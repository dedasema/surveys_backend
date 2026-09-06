# tests/test_software2_phase2.py
import io
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.survey import (
    PlantillaEncuesta, PreguntaEncuesta, OpcionEncuesta,
    CampanaEncuesta, EntregaEncuesta, ConversacionEncuesta,
    RespuestaEncuesta, RespuestaPregunta
)
from app.models.suscriptor import Suscriptor
from app.models.regla_ramificacion import ReglaRamificacion
from app.models.audio_respuesta import AudioRespuesta
from app.services.multimodal_service import (
    validar_archivo_multimodal, interpretar_multimodal, transcribir_audio,
    MAX_FILE_SIZE_BYTES
)
from app.services.ramificacion_service import (
    detectar_sentimiento_o_baja_calificacion,
    generar_pregunta_seguimiento,
    seleccionar_siguiente_pregunta_adaptativa
)

client = TestClient(app)

# Helper fixture para preparar una entrega de encuesta con plantilla y preguntas
@pytest.fixture
def test_setup(db_session: Session):
    suscriptor = Suscriptor(
        nombre="Empresa Fase 2 Test",
        email=f"fase2_{uuid.uuid4().hex[:8]}@test.com",
        password_hash="fake",
        rol_id=1
    )
    db_session.add(suscriptor)
    db_session.commit()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Plantilla Adaptativa Fase 2",
        descripcion="Encuesta para evaluar atención y productos"
    )
    db_session.add(plantilla)
    db_session.commit()

    p1 = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        orden=1,
        texto="¿Cómo calificaría su experiencia general?",
        tipo_pregunta_id=2, # numérica
        obligatorio=True
    )
    p2 = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        orden=2,
        texto="¿Recomendaría nuestros servicios a un colega?",
        tipo_pregunta_id=1, # abierta
        obligatorio=False
    )
    p3 = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        orden=3,
        texto="¿Tiene alguna sugerencia adicional?",
        tipo_pregunta_id=1,
        obligatorio=False
    )
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña Test Fase 2",
        canal_id=1,
        estado_id=1
    )
    db_session.add(campana)
    db_session.commit()

    entrega = EntregaEncuesta(
        campana_id=campana.id,
        canal_id=1,
        estado_id=1
    )
    db_session.add(entrega)
    db_session.commit()

    return {
        "suscriptor": suscriptor,
        "plantilla": plantilla,
        "preguntas": [p1, p2, p3],
        "campana": campana,
        "entrega": entrega
    }

# ==============================================================================
# RF20: SERVICIO MULTIMODAL CENTRALIZADO (VALIDACIONES Y PROMPT)
# ==============================================================================

def test_rf20_multimodal_validation():
    # Audio permitido
    validar_archivo_multimodal(b"audio-bytes", "audio/mp3")
    validar_archivo_multimodal(b"audio-bytes", "audio/wav")
    validar_archivo_multimodal(b"audio-bytes", "audio/ogg")
    
    # Imagen permitida
    validar_archivo_multimodal(b"image-bytes", "image/png")
    validar_archivo_multimodal(b"image-bytes", "image/jpeg")

    # Formato no permitido
    with pytest.raises(ValueError) as exc:
        validar_archivo_multimodal(b"doc-bytes", "application/pdf")
    assert "no permitido" in str(exc.value).lower()

    # Tamaño excesivo (>15MB)
    fake_large_data = b"0" * (MAX_FILE_SIZE_BYTES + 1024)
    with pytest.raises(ValueError) as exc_size:
        validar_archivo_multimodal(fake_large_data, "audio/mp3")
    assert "supera el tamaño máximo" in str(exc_size.value).lower()

@pytest.mark.asyncio
async def test_rf20_multimodal_transcribe_audio_mocked():
    fake_audio = b"fake-audio-bytes-wav"
    with patch("app.services.multimodal_service.interpretar_multimodal", new_callable=AsyncMock) as mock_interp:
        mock_interp.return_value = {"texto": "La comida llegó fría y tarde", "interpretacion": None}
        texto = await transcribir_audio(fake_audio, "audio/wav")
        assert texto == "La comida llegó fría y tarde"
        mock_interp.assert_called_once()

# ==============================================================================
# RF18: INGESTA Y TRANSCRIPCIÓN DE VOZ
# ==============================================================================

def test_rf18_subir_audio_respuesta_success(client: TestClient, test_setup):
    entrega = test_setup["entrega"]
    p1 = test_setup["preguntas"][0]

    with patch("app.routers.audio_respuestas_router.transcribir_audio", new_callable=AsyncMock) as mock_transcribe:
        mock_transcribe.return_value = "Muy contento con la rapidez del envío"

        audio_content = b"ID3v2-fake-mp3-stream-data"
        files = {
            "archivo": ("respuesta_voz.mp3", io.BytesIO(audio_content), "audio/mp3")
        }
        data = {
            "pregunta_id": str(p1.id)
        }

        response = client.post(f"/encuestas/{entrega.id}/audio-respuesta", files=files, data=data)
        assert response.status_code == 201
        res_data = response.json()
        assert res_data["entrega_id"] == str(entrega.id)
        assert res_data["pregunta_id"] == str(p1.id)
        assert res_data["estado_transcripcion"] == "completado"
        assert res_data["transcripcion_texto"] == "Muy contento con la rapidez del envío"
        assert "/uploads/audio/" in res_data["archivo_url"]

        # Consultar estado individual
        audio_id = res_data["id"]
        status_res = client.get(f"/encuestas/audio-respuesta/{audio_id}/estado")
        assert status_res.status_code == 200
        assert status_res.json()["transcripcion_texto"] == "Muy contento con la rapidez del envío"

def test_rf18_subir_audio_invalid_format(client: TestClient, test_setup):
    entrega = test_setup["entrega"]
    files = {
        "archivo": ("documento.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")
    }
    response = client.post(f"/encuestas/{entrega.id}/audio-respuesta", files=files)
    assert response.status_code == 400
    assert "no permitido" in response.json()["detail"].lower()

# ==============================================================================
# RF17 & RF17b: RAMIFICACIÓN ADAPTATIVA Y PREGUNTA GENERATIVA
# ==============================================================================

def test_rf17_deteccion_sentimiento_negativo():
    # Calificación baja
    assert detectar_sentimiento_o_baja_calificacion("Normal", puntuacion=1.0) is True
    assert detectar_sentimiento_o_baja_calificacion("Normal", puntuacion=2.0) is True
    assert detectar_sentimiento_o_baja_calificacion("Normal", puntuacion=4.0) is False

    # Palabras clave negativas
    assert detectar_sentimiento_o_baja_calificacion("Fue un pésimo servicio, muy mala atención") is True
    assert detectar_sentimiento_o_baja_calificacion("Horrible experiencia, nunca más vuelvo") is True
    assert detectar_sentimiento_o_baja_calificacion("Excelente servicio, todo impecable", puntuacion=5.0) is False

@pytest.mark.asyncio
async def test_rf17_regla_deterministica(db_session: Session, test_setup):
    plantilla = test_setup["plantilla"]
    p1 = test_setup["preguntas"][0]
    p3 = test_setup["preguntas"][2]

    # Crear regla determinística: Si en p1 dice 'soporte', saltar directamente a p3
    regla = ReglaRamificacion(
        plantilla_id=plantilla.id,
        pregunta_origen_id=p1.id,
        condicion_semantica="soporte",
        pregunta_destino_id=p3.id,
        es_fin_encuesta=False,
        orden_prioridad=1
    )
    db_session.add(regla)
    db_session.commit()

    decision = await seleccionar_siguiente_pregunta_adaptativa(
        db=db_session,
        plantilla_id=plantilla.id,
        pregunta_actual_id=p1.id,
        respuesta_actual_texto="Tuve un problema con el soporte técnico",
        historial=[],
        preguntas_respondidas_ids=[str(p1.id)]
    )
    assert decision["fin_encuesta"] is False
    assert decision["siguiente_pregunta_id"] == str(p3.id)
    assert "determinística" in decision["justificacion"]

def test_rf17_rf17b_flujo_adaptativo_completo(client: TestClient, db_session: Session, test_setup):
    entrega = test_setup["entrega"]
    p1, p2, p3 = test_setup["preguntas"]

    # 1. Iniciar encuesta adaptativa
    init_res = client.post(f"/encuestas/adaptativa/{entrega.id}/iniciar")
    assert init_res.status_code == 200
    data_init = init_res.json()
    assert data_init["fin_encuesta"] is False
    assert data_init["es_generativa"] is False
    assert data_init["siguiente_pregunta"]["id"] == str(p1.id)

    # 2. Responder P1 con insatisfacción extrema -> Debe disparar RF17b (pregunta generativa empática)
    with patch("app.routers.encuestas_adaptativas_router.generar_pregunta_seguimiento", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "¿Podrías detallarnos qué inconveniente específico tuviste con la atención?"

        resp1 = client.post(f"/encuestas/adaptativa/{entrega.id}/responder", json={
            "pregunta_id": str(p1.id),
            "texto": "Pésimo servicio y atención horrible",
            "numero": 1.0
        })

        assert resp1.status_code == 200
        data_r1 = resp1.json()
        assert data_r1["fin_encuesta"] is False
        assert data_r1["es_generativa"] is True
        assert data_r1["siguiente_pregunta"]["id"] is None
        assert data_r1["siguiente_pregunta"]["texto"] == "¿Podrías detallarnos qué inconveniente específico tuviste con la atención?"
        mock_gen.assert_called_once()

    # 3. Responder la pregunta generativa
    # Ahora debe limpiar la pregunta generativa y continuar con el banco (p2 o p3)
    with patch("app.routers.encuestas_adaptativas_router.seleccionar_siguiente_pregunta_adaptativa", new_callable=AsyncMock) as mock_sel:
        mock_sel.return_value = {
            "siguiente_pregunta_id": str(p2.id),
            "fin_encuesta": False,
            "justificacion": "Avanzar a P2 del banco"
        }

        resp2 = client.post(f"/encuestas/adaptativa/{entrega.id}/responder", json={
            "texto": "El personal fue descortés y tardaron 2 horas"
        })

        assert resp2.status_code == 200
        data_r2 = resp2.json()
        assert data_r2["fin_encuesta"] is False
        assert data_r2["es_generativa"] is False
        assert data_r2["siguiente_pregunta"]["id"] == str(p2.id)

    # 4. Responder P2 con otra queja negativa -> NO debe disparar generativa de nuevo porque el límite es 1 (RF17b)
    with patch("app.routers.encuestas_adaptativas_router.seleccionar_siguiente_pregunta_adaptativa", new_callable=AsyncMock) as mock_sel2:
        mock_sel2.return_value = {
            "siguiente_pregunta_id": str(p3.id),
            "fin_encuesta": False,
            "justificacion": "Límite generativo alcanzado, avanzar a P3"
        }

        resp3 = client.post(f"/encuestas/adaptativa/{entrega.id}/responder", json={
            "pregunta_id": str(p2.id),
            "texto": "Terrible, jamás los recomendaría a nadie",
            "numero": 1.0
        })

        assert resp3.status_code == 200
        data_r3 = resp3.json()
        # Debe haber ido a P3 directamente, no a otra generativa
        assert data_r3["es_generativa"] is False
        assert data_r3["siguiente_pregunta"]["id"] == str(p3.id)

    # 5. Responder P3 finalizando la encuesta
    with patch("app.routers.encuestas_adaptativas_router.seleccionar_siguiente_pregunta_adaptativa", new_callable=AsyncMock) as mock_sel3:
        mock_sel3.return_value = {
            "siguiente_pregunta_id": None,
            "fin_encuesta": True,
            "justificacion": "No quedan más preguntas en el banco"
        }

        resp4 = client.post(f"/encuestas/adaptativa/{entrega.id}/responder", json={
            "pregunta_id": str(p3.id),
            "texto": "Mejoren la capacitación"
        })

        assert resp4.status_code == 200
        data_r4 = resp4.json()
        assert data_r4["fin_encuesta"] is True
        assert data_r4["siguiente_pregunta"] is None
        assert "hash_integridad" in data_r4
        assert len(data_r4["hash_integridad"]) == 64

    # 6. Verificar persistencia en Base de Datos y Hash-Chain (RNF8)
    conv_db = db_session.query(ConversacionEncuesta).filter_by(entrega_id=entrega.id).first()
    assert conv_db.completada is True
    assert conv_db.preguntas_generativas_usadas == 1

    resp_db = db_session.query(RespuestaEncuesta).filter_by(entrega_id=entrega.id).first()
    assert resp_db is not None
    assert resp_db.hash == data_r4["hash_integridad"]
    assert resp_db.hash_anterior is not None
