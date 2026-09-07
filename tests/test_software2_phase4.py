# tests/test_software2_phase4.py
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
from app.models.agregado_campana import AgregadoCampana
from app.models.rag_consulta import RagConsulta
from app.services.websocket_manager import ws_manager
from app.services.predictivo_service import obtener_metricas_predictivas
from app.services.rag_service import consultar_asistente_rag

client = TestClient(app)

@pytest.fixture
def phase4_setup(db_session: Session):
    suscriptor = Suscriptor(
        nombre="Empresa Fase 4 Test",
        email=f"fase4_{uuid.uuid4().hex[:8]}@test.com",
        password_hash="fake",
        rol_id=1
    )
    db_session.add(suscriptor)
    db_session.commit()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Plantilla Fase 4 Analítica",
        descripcion="Encuesta para análisis predictivo y RAG"
    )
    db_session.add(plantilla)
    db_session.commit()

    pregunta = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        orden=1,
        texto="¿Cómo califica el tiempo de atención y soporte?",
        tipo_pregunta_id=1,
        obligatorio=True
    )
    db_session.add(pregunta)
    db_session.commit()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña Analítica Q4",
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
# RF24: WEBSOCKETS Y SINCRONIZACIÓN EN VIVO
# ==============================================================================

def test_rf24_websocket_campana_ping_pong():
    campana_id = str(uuid.uuid4())
    with client.websocket_connect(f"/ws/campanas/{campana_id}") as websocket:
        # Recibir mensaje de bienvenida
        initial_msg = websocket.receive_json()
        assert initial_msg["type"] == "conexion_establecida"
        assert initial_msg["payload"]["campana_id"] == campana_id

        # Enviar ping
        websocket.send_json({"action": "ping"})
        response = websocket.receive_json()
        assert response["type"] == "pong"

def test_rf24_websocket_general():
    with client.websocket_connect("/ws/general") as websocket:
        initial_msg = websocket.receive_json()
        assert initial_msg["type"] == "conexion_establecida"

        # Ping
        websocket.send_json({"action": "ping"})
        response = websocket.receive_json()
        assert response["type"] == "pong"

# ==============================================================================
# RF23: DASHBOARD PREDICTIVO Y AGREGADOS POR PERÍODO
# ==============================================================================

def test_rf23_registrar_agregados_y_metricas_predictivas(client: TestClient, phase4_setup):
    campana = phase4_setup["campana"]

    # 1. Registrar cohortes agregadas históricas
    periodos_mock = [
        {"periodo": "Sem 1", "total_respuestas": 40, "promedio_satisfaccion": 75.0, "orden_periodo": 1},
        {"periodo": "Sem 2", "total_respuestas": 55, "promedio_satisfaccion": 78.0, "orden_periodo": 2},
        {"periodo": "Sem 3", "total_respuestas": 72, "promedio_satisfaccion": 81.5, "orden_periodo": 3},
        {"periodo": "Sem 4", "total_respuestas": 90, "promedio_satisfaccion": 84.0, "orden_periodo": 4},
    ]

    for p in periodos_mock:
        res = client.post(f"/campanas/{campana.id}/agregados", json=p)
        assert res.status_code == 201

    # 2. Consultar predicción de respuestas
    with patch("app.services.predictivo_service.call_gemini_text", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = "Se proyecta un crecimiento sostenido del 18% para las próximas dos semanas."

        resp_pred = client.get(f"/campanas/{campana.id}/predictivo?metrica=respuestas&granularidad=semanal")
        assert resp_pred.status_code == 200
        data = resp_pred.json()

        assert data["total_periodos_historicos"] == 4
        assert data["proxima_proyeccion"] > 90.0 # Por tendencia ascendente
        assert data["tendencia_porcentual"] > 0
        assert data["nivel_confianza"] >= 80.0
        assert len(data["puntos"]) == 6 # 4 históricos + 2 proyectados
        assert data["puntos"][-1]["proyectado"] is not None
        assert data["puntos"][-1]["limite_inferior"] is not None

    # 3. Consultar predicción global
    with patch("app.services.predictivo_service.call_gemini_text", new_callable=AsyncMock) as mock_gemini_global:
        mock_gemini_global.return_value = "Tendencia de satisfacción estable a nivel global."
        resp_global = client.get("/predictivo?metrica=satisfaccion&granularidad=semanal")
        assert resp_global.status_code == 200
        assert resp_global.json()["total_periodos_historicos"] >= 2

# ==============================================================================
# RF26: ASISTENTE RAG CON BÚSQUEDA VECTORIAL Y CITAS
# ==============================================================================

@pytest.mark.asyncio
async def test_rf26_asistente_rag_consultar_y_citas(client: TestClient, db_session: Session, phase4_setup):
    campana = phase4_setup["campana"]
    pregunta = phase4_setup["pregunta"]

    # Insertar respuestas reales en BD para recuperación semántica
    respuestas_texto = [
        "El tiempo de espera en el chat de soporte superó los 30 minutos.",
        "La atención telefónica fue impecable y resolvieron mi duda de inmediato.",
        "Cobro duplicado en mi tarjeta de crédito al renovar el plan."
    ]

    for t in respuestas_texto:
        entrega = EntregaEncuesta(campana_id=campana.id, canal_id=1, estado_id=2)
        db_session.add(entrega)
        db_session.commit()

        resp = RespuestaEncuesta(entrega_id=entrega.id)
        db_session.add(resp)
        db_session.commit()

        rp = RespuestaPregunta(respuesta_id=resp.id, pregunta_id=pregunta.id, texto=t)
        db_session.add(rp)
        db_session.commit()

    # 1. Consultar al asistente RAG
    with patch("app.services.rag_service.call_gemini_text", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = "Los usuarios reportan demoras en los tiempos de espera del soporte, aunque valoran la atención telefónica."

        res = client.post("/asistente/consultar", json={
            "pregunta": "¿Cuáles son las quejas sobre los tiempos de atención?",
            "campana_id": str(campana.id)
        })

        assert res.status_code == 200
        data = res.json()
        assert "respuesta" in data
        assert len(data["respuesta"]) > 20
        assert "fuentes_citadas" in data
        assert len(data["fuentes_citadas"]) > 0

        cita = data["fuentes_citadas"][0]
        assert cita["tipo"] == "respuesta"
        assert "fragmento" in cita
        assert "similitud_score" in cita
        assert cita["campana"] == campana.nombre

    # 2. Consultar historial de RAG
    res_historial = client.get(f"/asistente/historial?campana_id={campana.id}")
    assert res_historial.status_code == 200
    historial = res_historial.json()
    assert len(historial) >= 1
    assert "¿Cuáles son las quejas sobre los tiempos de atención?" in historial[0]["pregunta"]
