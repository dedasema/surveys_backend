import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import settings
from app.core.rate_limit import _request_history
from app.models.contacto import Contacto
from app.models.survey import (
    CampanaEncuesta,
    Destinatario,
    EntregaEncuesta,
    PlantillaEncuesta,
    PreguntaEncuesta,
)
from app.models.suscriptor import Suscriptor


@pytest.fixture(autouse=True)
def clean_rate_limits():
    _request_history.clear()
    yield
    _request_history.clear()


# ==============================================================================
# 1. DEMO PERSONALIZADA (POST /solicitar-demo)
# ==============================================================================

def test_solicitar_demo_endpoint(client, db_session):
    """
    POST /solicitar-demo:
    - Retorna status 200 y JSON: {"success": true, "message": "Solicitud de demo..."}
    - Registra la solicitud en la base de datos (tabla contacto)
    - Envía notificación por correo a la casilla comercial (soporte@desesoft.com)
      con asunto '🚀 Nueva solicitud de Demo Personalizada - SurveySaaS'
    """
    with patch("app.routers.contacto_router._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        demo_payload = {
            "email": "demo.prospecto@corporativo.bo",
            "nombre": "Mariana Gómez",
            "empresa": "Tech Solutions Bolivia",
            "telefono": "+591 70012345",
        }

        res = client.post("/solicitar-demo", json=demo_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["message"] == "Solicitud de demo recibida con éxito"

        # Verificar en base de datos
        db_session.expire_all()
        contacto_db = (
            db_session.query(Contacto)
            .filter(Contacto.email == "demo.prospecto@corporativo.bo")
            .order_by(Contacto.creado_en.desc())
            .first()
        )
        assert contacto_db is not None
        assert contacto_db.nombre == "Mariana Gómez"
        assert contacto_db.empresa == "Tech Solutions Bolivia"
        assert contacto_db.tipo == "comercial"
        assert contacto_db.origen == "producto"

        # Verificar despacho de correo comercial
        assert mock_send.call_count >= 1
        llamadas = mock_send.call_args_list
        # Primera llamada debe ser la alerta comercial al correo corporativo
        call_comercial = llamadas[0]
        destinatario = call_comercial.kwargs.get("destinatario_email") or (
            call_comercial.args[0] if len(call_comercial.args) > 0 else None
        )
        asunto = call_comercial.kwargs.get("asunto") or (
            call_comercial.args[2] if len(call_comercial.args) > 2 else None
        )
        html = (
            call_comercial.kwargs.get("html_content")
            or call_comercial.kwargs.get("cuerpo_html")
            or (call_comercial.args[3] if len(call_comercial.args) > 3 else "")
        )

        assert destinatario == (settings.COMERCIAL_EMAIL or "soporte@desesoft.com")
        assert asunto == "🚀 Nueva solicitud de Demo Personalizada - SurveySaaS"
        assert html is not None
        assert "demo.prospecto@corporativo.bo" in html
        assert "Tech Solutions Bolivia" in html


def test_solicitar_demo_alias_leads_demo(client, db_session):
    """
    POST /leads/demo debe responder 200 con el mismo contrato y registrar en BD.
    """
    with patch("app.routers.contacto_router._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        res = client.post(
            "/leads/demo",
            json={
                "email": "lead.interesado@empresa.com",
                "nombre": "Roberto Dávila",
                "empresa": "Constructora Dávila",
            },
        )
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert res.json()["message"] == "Solicitud de demo recibida con éxito"

        contacto = (
            db_session.query(Contacto)
            .filter(Contacto.email == "lead.interesado@empresa.com")
            .first()
        )
        assert contacto is not None
        assert contacto.tipo == "comercial"


# ==============================================================================
# 2. COMPATIBILIDAD CON POST /contacto (COMERCIAL, SOPORTE, DERECHOS)
# ==============================================================================

def test_contacto_comercial_routes_to_comercial_email(client, db_session):
    """
    POST /contacto:
    - Si tipo == 'comercial', envía la alerta por correo al equipo comercial.
    """
    with patch("app.routers.contacto_router._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        res = client.post(
            "/contacto",
            json={
                "nombre": "Comprador Potencial",
                "email": "comprador@negocios.bo",
                "empresa": "Grupo Inversor",
                "tipo": "comercial",
                "mensaje": "Quisiera cotizar 500 encuestas mensuales.",
            },
        )
        assert res.status_code == 201

        assert mock_send.called
        call_0 = mock_send.call_args
        destinatario = call_0.kwargs.get("destinatario_email") or (
            call_0.args[0] if len(call_0.args) > 0 else None
        )
        assert destinatario == (settings.COMERCIAL_EMAIL or "soporte@desesoft.com")


# ==============================================================================
# 3. CONSENTIMIENTO EN POST /encuestas/responder/{token}
# ==============================================================================

def test_responder_encuesta_consentimiento_audit(client, db_session):
    """
    POST /encuestas/responder/{token}:
    - Acepta consentimiento_aceptado: bool = Query(True) o header X-Consentimiento-Aceptado.
    - Guarda la confirmación y marca temporal del consentimiento en entrega_encuesta.
    """
    suscriptor = Suscriptor(
        id=uuid.uuid4(),
        nombre="Empresa Audit Consent",
        email=f"audit_consent_{uuid.uuid4().hex[:6]}@empresa.com",
        password_hash="test_password_hash",
        estado="activo",
    )
    db_session.add(suscriptor)
    db_session.flush()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Plantilla Consentimiento Email",
        descripcion="Test",
    )
    db_session.add(plantilla)
    db_session.flush()

    pregunta = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        texto="¿Cómo evalúa la atención recibida?",
        tipo_pregunta_id=1,
        orden=1,
    )
    db_session.add(pregunta)
    db_session.flush()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña Email Token",
        canal_id=1,
        estado_id=2,  # activa
    )
    db_session.add(campana)
    db_session.flush()

    dest = Destinatario(
        suscriptor_id=suscriptor.id,
        nombre="Encuestado Token",
        email="encuestado.token@correo.com",
    )
    db_session.add(dest)
    db_session.flush()

    entrega = EntregaEncuesta(
        campana_id=campana.id,
        destinatario_id=dest.id,
        canal_id=1,
    )
    db_session.add(entrega)
    db_session.commit()

    # 1. Responder con parámetro query consentimiento_aceptado=true
    respuestas_body = [
        {
            "pregunta_id": str(pregunta.id),
            "tipo_respuesta": "texto",
            "texto": "Excelente atención.",
        }
    ]

    res = client.post(
        f"/encuestas/responder/{entrega.id}?consentimiento_aceptado=true",
        json=respuestas_body,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["consentimiento_aceptado"] is True
    assert data["consentimiento_en"] is not None

    # Verificar en BD
    db_session.expire_all()
    entrega_db = db_session.get(EntregaEncuesta, entrega.id)
    assert entrega_db.consentimiento_aceptado is True
    assert entrega_db.consentimiento_en is not None


def test_responder_encuesta_consentimiento_header(client, db_session):
    """
    POST /encuestas/responder/{token} con header X-Consentimiento-Aceptado: true
    """
    suscriptor = Suscriptor(
        id=uuid.uuid4(),
        nombre="Empresa Header Consent",
        email=f"header_consent_{uuid.uuid4().hex[:6]}@empresa.com",
        password_hash="test_password_hash",
        estado="activo",
    )
    db_session.add(suscriptor)
    db_session.flush()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Plantilla Header Consent",
        descripcion="Test",
    )
    db_session.add(plantilla)
    db_session.flush()

    pregunta = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        texto="Comentarios adicionales",
        tipo_pregunta_id=1,
        orden=1,
    )
    db_session.add(pregunta)
    db_session.flush()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña Header Token",
        canal_id=1,
        estado_id=2,
    )
    db_session.add(campana)
    db_session.flush()

    dest = Destinatario(
        suscriptor_id=suscriptor.id,
        nombre="Encuestado Header",
        email="encuestado.header@correo.com",
    )
    db_session.add(dest)
    db_session.flush()

    entrega = EntregaEncuesta(
        campana_id=campana.id,
        destinatario_id=dest.id,
        canal_id=1,
    )
    db_session.add(entrega)
    db_session.commit()

    res = client.post(
        f"/encuestas/responder/{entrega.id}",
        headers={"X-Consentimiento-Aceptado": "true"},
        json=[
            {
                "pregunta_id": str(pregunta.id),
                "tipo_respuesta": "texto",
                "texto": "Todo perfecto.",
            }
        ],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["consentimiento_aceptado"] is True

    db_session.expire_all()
    entrega_db = db_session.get(EntregaEncuesta, entrega.id)
    assert entrega_db.consentimiento_aceptado is True
    assert entrega_db.consentimiento_en is not None
