# tests/test_software2_phase3.py
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.survey import (
    PlantillaEncuesta, PreguntaEncuesta, CampanaEncuesta,
    EntregaEncuesta, RespuestaEncuesta, RespuestaPregunta
)
from app.models.suscriptor import Suscriptor
from app.models.fraude_flag import FraudeFlag
from app.models.agente_decision import AgenteDecision
from app.services.embedding_service import (
    generar_embedding, similitud_coseno, _generar_embedding_fallback
)
from app.services.fraude_service import (
    es_texto_gibberish_o_spam, evaluar_respuesta_antifraude
)
from app.services.agente_service import evaluar_evento_con_agente

client = TestClient(app)

@pytest.fixture
def phase3_setup(db_session: Session):
    suscriptor = Suscriptor(
        nombre="Empresa Fase 3 Test",
        email=f"fase3_{uuid.uuid4().hex[:8]}@test.com",
        password_hash="fake",
        rol_id=1
    )
    db_session.add(suscriptor)
    db_session.commit()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Plantilla Fase 3 Inteligencia",
        descripcion="Evaluación de feedback semántico"
    )
    db_session.add(plantilla)
    db_session.commit()

    pregunta = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        orden=1,
        texto="¿Qué opinión tiene sobre el servicio brindado?",
        tipo_pregunta_id=1,
        obligatorio=True
    )
    db_session.add(pregunta)
    db_session.commit()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña Inteligencia Q3",
        canal_id=1,
        estado_id=1
    )
    db_session.add(campana)
    db_session.commit()

    return {
        "suscriptor": suscriptor,
        "plantilla": plantilla,
        "pregunta": pregunta,
        "campana": campana
    }

# ==============================================================================
# RF22: CLUSTERING SEMÁNTICO CON PGVECTOR Y GEMINI
# ==============================================================================

def test_rf22_embedding_and_cosine_similarity():
    # 1. Determinismo y normalización de fallback
    v1 = _generar_embedding_fallback("Excelente atención en el local")
    v2 = _generar_embedding_fallback("Excelente atención en el local")
    assert len(v1) == 768
    assert len(v2) == 768
    sim_identica = similitud_coseno(v1, v2)
    assert pytest.approx(sim_identica, rel=1e-3) == 1.0

    # 2. Textos distintos
    v3 = _generar_embedding_fallback("El producto llegó roto y muy tarde")
    sim_distinta = similitud_coseno(v1, v3)
    assert sim_distinta < 0.90

@pytest.mark.asyncio
async def test_rf22_clustering_endpoint(client: TestClient, db_session: Session, phase3_setup):
    campana = phase3_setup["campana"]
    pregunta = phase3_setup["pregunta"]

    # Crear 3 respuestas con opiniones variadas
    textos_respuestas = [
        "Muy buena y ágil atención del personal",
        "El soporte fue rápido y amable en todo momento",
        "Los precios son elevados para el mercado"
    ]

    for t in textos_respuestas:
        entrega = EntregaEncuesta(campana_id=campana.id, canal_id=1, estado_id=2)
        db_session.add(entrega)
        db_session.commit()

        resp = RespuestaEncuesta(entrega_id=entrega.id, raw_payload={"texto": t})
        db_session.add(resp)
        db_session.commit()

        rp = RespuestaPregunta(respuesta_id=resp.id, pregunta_id=pregunta.id, texto=t)
        db_session.add(rp)
        db_session.commit()

    with patch("app.services.clustering_service.call_gemini_text", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = '{"etiqueta_ia": "Atención y Rapidez", "resumen_ia": "Destacan la amabilidad del soporte."}'

        response = client.get(f"/campanas/{campana.id}/clusters")
        assert response.status_code == 200
        data = response.json()
        assert data["campana_id"] == str(campana.id)
        assert data["total_clusters"] > 0
        c1 = data["clusters"][0]
        assert "etiqueta_ia" in c1
        assert "resumen_ia" in c1
        assert c1["total_respuestas"] > 0
        assert "proporcion" in c1
        assert len(c1["ejemplos_respuestas"]) > 0

# ==============================================================================
# RF21: DETECCIÓN Y REVISIÓN DE FRAUDE
# ==============================================================================

def test_rf21_deteccion_gibberish_o_spam():
    # Keyboard mashing
    es_spam, conf, just = es_texto_gibberish_o_spam("asdfghjklqwerty")
    assert es_spam is True
    assert conf >= 0.85

    # Repetición extrema
    es_spam2, conf2, _ = es_texto_gibberish_o_spam("aaaaaaaaaaa")
    assert es_spam2 is True
    assert conf2 >= 0.90

    # Texto legítimo
    es_spam3, _, _ = es_texto_gibberish_o_spam("La experiencia de compra fue muy buena y rápida")
    assert es_spam3 is False

@pytest.mark.asyncio
async def test_rf21_evaluar_antifraude_y_resolver(client: TestClient, db_session: Session, phase3_setup):
    campana = phase3_setup["campana"]
    pregunta = phase3_setup["pregunta"]

    # Crear entrega y respuesta con texto spam evidente
    entrega = EntregaEncuesta(campana_id=campana.id, canal_id=1, estado_id=1)
    db_session.add(entrega)
    db_session.commit()

    resp = RespuestaEncuesta(entrega_id=entrega.id)
    db_session.add(resp)
    db_session.commit()

    rp = RespuestaPregunta(respuesta_id=resp.id, pregunta_id=pregunta.id, texto="asdfghjkl 12345 qwert")
    db_session.add(rp)
    db_session.commit()

    # 1. Evaluar antifraude
    flag = await evaluar_respuesta_antifraude(db_session, resp.id, canal="web")
    assert flag is not None
    assert flag.tipo_senal == "regla"
    assert flag.estado == "pendiente"

    # 2. Consultar cola de fraude via API
    res_cola = client.get(f"/fraude/cola?campana_id={campana.id}")
    assert res_cola.status_code == 200
    cola_data = res_cola.json()
    assert len(cola_data) >= 1
    flag_item = next(f for f in cola_data if f["id"] == str(flag.id))
    assert flag_item["estado"] == "pendiente"
    assert flag_item["tipo_senal"] == "regla"

    # 3. Resolver la marca confirmando fraude
    res_resolver = client.post(f"/fraude/{flag.id}/resolver", json={"accion": "confirmar_fraude"})
    assert res_resolver.status_code == 200
    assert res_resolver.json()["estado"] == "confirmado_fraude"

    # Verificar en BD
    flag_db = db_session.query(FraudeFlag).filter_by(id=flag.id).first()
    assert flag_db.estado == "confirmado_fraude"

# ==============================================================================
# RF25: AGENTE AUTÓNOMO Y REGISTRO DE DECISIONES
# ==============================================================================

@pytest.mark.asyncio
async def test_rf25_agente_autonomo_decision_log(client: TestClient, db_session: Session, phase3_setup):
    campana = phase3_setup["campana"]

    # 1. Disparar evaluación de evento crítico (queja severa)
    with patch("app.services.agente_service.call_gemini_text", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = '''{
          "tool_ejecutada": "escalar_caso_soporte",
          "parametros": {
            "prioridad": "alta",
            "departamento": "Atención al Cliente",
            "motivo": "Insatisfacción crítica reportada",
            "ticket_externo": false
          },
          "razonamiento_ia": "El cliente manifestó una queja severa que amerita intervención inmediata."
        }'''

        eval_res = client.post("/agente/evaluar", json={
            "campana_id": str(campana.id),
            "trigger_evento": "Respuesta con queja severa y calificación 1"
        })

        assert eval_res.status_code == 201
        data_dec = eval_res.json()
        assert data_dec["tool_ejecutada"] == "escalar_caso_soporte"
        assert data_dec["parametros"]["prioridad"] == "alta"
        assert data_dec["estado"] == "ejecutado"
        assert data_dec["tiempo_ejecucion_ms"] >= 0

        # 2. Consultar historial de decisiones del agente
        dec_id = data_dec["id"]
        list_res = client.get(f"/agente/decisiones?campana_id={campana.id}")
        assert list_res.status_code == 200
        decisiones = list_res.json()
        assert any(d["id"] == dec_id for d in decisiones)
