import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.core.rate_limit import _request_history
from app.models.audit_log import AuditLog
from app.models.audio_respuesta import AudioRespuesta
from app.models.contacto import Contacto
from app.models.subscription import PlanSuscripcion
from app.models.survey import (
    CampanaEncuesta,
    Destinatario,
    EntregaEncuesta,
    PlantillaEncuesta,
    PreguntaEncuesta,
    RespuestaEncuesta,
)
from app.models.suscriptor import Suscriptor
from app.services.plan_limits_service import get_effective_entregas_limit


@pytest.fixture(autouse=True)
def clean_rate_limits():
    _request_history.clear()
    yield
    _request_history.clear()


# ==============================================================================
# B1: CONTACT ENUMS & RATE LIMITING
# ==============================================================================

def test_contacto_validation_invalid_enums(client):
    """
    POST /contacto debe rechazar valores desconocidos de origen y tipo con 422.
    """
    # Origen inválido
    res = client.post(
        "/contacto",
        json={
            "nombre": "Test User",
            "email": "test@test.com",
            "origen": "invalido",
            "tipo": "comercial",
            "mensaje": "Mensaje de prueba",
        },
    )
    assert res.status_code == 422

    # Tipo inválido
    res2 = client.post(
        "/contacto",
        json={
            "nombre": "Test User",
            "email": "test@test.com",
            "origen": "producto",
            "tipo": "tipo_desconocido",
            "mensaje": "Mensaje de prueba",
        },
    )
    assert res2.status_code == 422


def test_contacto_rate_limit(client):
    """
    POST /contacto debe limitar las peticiones por IP a 5 por minuto.
    La 6ta petición debe retornar HTTP 429 Too Many Requests.
    """
    _request_history.clear()
    with patch("app.routers.contacto_router._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        for i in range(5):
            res = client.post(
                "/contacto",
                json={
                    "nombre": f"Persona {i}",
                    "email": f"persona{i}@test.com",
                    "origen": "producto",
                    "tipo": "comercial",
                    "mensaje": "Consulta de prueba",
                },
            )
            assert res.status_code == 201

        # 6ta petición debe ser bloqueada por rate limit
        res_blocked = client.post(
            "/contacto",
            json={
                "nombre": "Persona 6",
                "email": "persona6@test.com",
                "origen": "producto",
                "tipo": "comercial",
                "mensaje": "Consulta bloqueada",
            },
        )
        assert res_blocked.status_code == 429
        assert "Demasiadas solicitudes" in res_blocked.json()["detail"]


# ==============================================================================
# B2: DERECHOS SOBRE LOS DATOS (ARCO) & AUDIT LOG
# ==============================================================================

def test_derechos_datos_erasure_procedure(client, db_session, admin_headers):
    """
    Verifica que el procedimiento de eliminación de datos de una persona:
    1. Elimine las respuestas y los audios asociados.
    2. Registre el evento en la bitácora de auditoría (AuditLog).
    3. Permita al administrador consultar solicitudes de tipo derechos_datos.
    """
    # 1. Crear suscriptor y campaña con respuestas
    suscriptor = Suscriptor(
        id=uuid.uuid4(),
        nombre="Empresa Test ARCO",
        email=f"arco_{uuid.uuid4().hex[:6]}@empresa.com",
        password_hash="test_password_hash",
        estado="activo",
    )
    db_session.add(suscriptor)
    db_session.flush()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Encuesta ARCO",
        descripcion="Test",
    )
    db_session.add(plantilla)
    db_session.flush()

    pregunta = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        texto="¿Su opinión?",
        tipo_pregunta_id=1,
        orden=1,
    )
    db_session.add(pregunta)
    db_session.flush()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña ARCO",
        canal_id=1,
        estado_id=2,  # activa
    )
    db_session.add(campana)
    db_session.flush()

    target_email = "ciudadano@privacidad.org"

    destinatario = Destinatario(
        suscriptor_id=suscriptor.id,
        nombre="Ciudadano Privacidad",
        email=target_email,
    )
    db_session.add(destinatario)
    db_session.flush()

    # Entrega asociada a este ciudadano
    entrega = EntregaEncuesta(
        campana_id=campana.id,
        destinatario_id=destinatario.id,
        canal_id=1,
        consentimiento_aceptado=True,
    )
    db_session.add(entrega)
    db_session.flush()

    # Respuesta
    resp = RespuestaEncuesta(
        entrega_id=entrega.id,
    )
    db_session.add(resp)

    # Audio respuesta
    audio = AudioRespuesta(
        entrega_id=entrega.id,
        pregunta_id=pregunta.id,
        archivo_url="/uploads/audios/test_privacidad.wav",
        formato="wav",
        transcripcion_texto="Mi audio privado sensible",
    )
    db_session.add(audio)

    # Contacto de derechos de datos registrado
    contacto_arco = Contacto(
        nombre="Ciudadano Privacidad",
        email=target_email,
        origen="producto",
        tipo="derechos_datos",
        mensaje="Solicito la eliminación completa de mis respuestas.",
    )
    db_session.add(contacto_arco)
    db_session.commit()

    # 2. Consultar lista filtrada por tipo derechos_datos como admin
    res_list = client.get("/contacto/consultas?tipo=derechos_datos", headers=admin_headers)
    assert res_list.status_code == 200
    consultas = res_list.json()
    assert any(c["email"] == target_email and c["tipo"] == "derechos_datos" for c in consultas)

    # 3. Ejecutar endpoint de eliminación de datos de B2
    res_elim = client.post(
        "/contacto/derechos-datos/eliminar",
        json={
            "email": target_email,
            "motivo": "Solicitud de ejercicio de derechos ARCO",
        },
        headers=admin_headers,
    )
    assert res_elim.status_code == 200
    data_elim = res_elim.json()
    assert data_elim["success"] is True
    assert data_elim["respuestas_eliminadas"] >= 1
    assert data_elim["audios_eliminados"] >= 1

    # 4. Verificar que se borraron en la BD
    db_session.expire_all()
    resp_check = (
        db_session.query(RespuestaEncuesta)
        .filter(RespuestaEncuesta.entrega_id == entrega.id)
        .all()
    )
    assert len(resp_check) == 0

    audio_check = (
        db_session.query(AudioRespuesta)
        .filter(AudioRespuesta.entrega_id == entrega.id)
        .all()
    )
    assert len(audio_check) == 0

    # 5. Verificar que se registró en AuditLog
    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.accion == "DERECHOS_DATOS_ELIMINACION")
        .order_by(AuditLog.creado_en.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.modulo == "DERECHOS_DATOS"
    assert audit_entry.detalles["persona_identificador"] == target_email


# ==============================================================================
# B3: CONSENTIMIENTO OBLIGATORIO EN ENCUESTAS PÚBLICAS
# ==============================================================================

def test_consentimiento_obligatorio_en_respuestas_publicas(client, db_session):
    """
    POST /public/entregas/{id}/respuestas:
    - Si consentimiento_aceptado no es True, responde 400 y no guarda nada.
    - Si es True, guarda la fecha y hora del consentimiento junto con la entrega.
    """
    suscriptor = Suscriptor(
        id=uuid.uuid4(),
        nombre="Empresa Consentimiento",
        email=f"consent_{uuid.uuid4().hex[:6]}@empresa.com",
        password_hash="test_password_hash",
        estado="activo",
    )
    db_session.add(suscriptor)
    db_session.flush()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Encuesta Consentimiento",
        descripcion="Test consentimiento",
    )
    db_session.add(plantilla)
    db_session.flush()

    pregunta = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        texto="¿Calificación?",
        tipo_pregunta_id=2,
        orden=1,
    )
    db_session.add(pregunta)
    db_session.flush()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña Consentimiento",
        canal_id=1,
        estado_id=2,  # activa
    )
    db_session.add(campana)
    db_session.flush()

    dest = Destinatario(
        suscriptor_id=suscriptor.id,
        nombre="Encuestado Test",
        email="encuestado@test.com",
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

    # 1. Intento sin consentimiento (False)
    payload_sin_consentimiento = {
        "consentimiento_aceptado": False,
        "respuestas_preguntas": [
            {
                "pregunta_id": str(pregunta.id),
                "texto": "Respuesta sin consentimiento",
            }
        ],
    }
    res_sin = client.post(
        f"/public/entregas/{entrega.id}/respuestas",
        json=payload_sin_consentimiento,
    )
    assert res_sin.status_code == 400
    assert "consentimiento informado" in res_sin.json()["detail"].lower()

    # Verificar que NO se guardaron respuestas
    db_session.expire_all()
    respuestas_guardadas = (
        db_session.query(RespuestaEncuesta)
        .filter(RespuestaEncuesta.entrega_id == entrega.id)
        .all()
    )
    assert len(respuestas_guardadas) == 0

    # 2. Intento con consentimiento_aceptado = True
    payload_con_consentimiento = {
        "consentimiento_aceptado": True,
        "respuestas_preguntas": [
            {
                "pregunta_id": str(pregunta.id),
                "texto": "Respuesta con consentimiento",
            }
        ],
    }
    res_con = client.post(
        f"/public/entregas/{entrega.id}/respuestas",
        json=payload_con_consentimiento,
    )
    assert res_con.status_code in (200, 201)

    # Verificar que se persistió y que consentimiento_en se registró
    db_session.expire_all()
    entrega_actualizada = db_session.get(EntregaEncuesta, entrega.id)
    assert entrega_actualizada.consentimiento_aceptado is True
    assert entrega_actualizada.consentimiento_en is not None


# ==============================================================================
# B5: PLANES Y CUPO ADICIONAL (BONUS)
# ==============================================================================

def test_planes_y_cupo_adicional(client, db_session, admin_headers):
    """
    Verifica que el administrador pueda asignar bono de cupo adicional
    y que el límite efectivo sea el límite del plan más el bono.
    """
    plan = db_session.query(PlanSuscripcion).filter(PlanSuscripcion.id == 1).first()
    if not plan:
        plan = PlanSuscripcion(
            id=1,
            nombre="Gratuito",
            precio_mensual=0,
            max_plantillas=3,
            max_campanas=1,
            max_entregas=100,
            max_operadores=1,
        )
        db_session.add(plan)
        db_session.commit()

    suscriptor = Suscriptor(
        id=uuid.uuid4(),
        nombre="Empresa Cupos",
        email=f"cupos_{uuid.uuid4().hex[:6]}@empresa.com",
        password_hash="test_password_hash",
        estado="activo",
        bono_entregas=0,
        bono_paginas_ocr=0,
        bono_minutos_voz=0,
    )
    db_session.add(suscriptor)
    db_session.commit()

    # Límite inicial sin bono
    limite_inicial, _, _ = get_effective_entregas_limit(db_session, suscriptor.id)
    assert limite_inicial == plan.max_entregas

    # Asignar bono mediante endpoint de administrador
    res_bonus = client.put(
        f"/admin/suscriptores/{suscriptor.id}/cupo-adicional",
        json={
            "bono_entregas": 500,
            "bono_paginas_ocr": 50,
            "bono_minutos_voz": 120,
        },
        headers=admin_headers,
    )
    assert res_bonus.status_code == 200
    data_bonus = res_bonus.json()
    assert data_bonus["resumen_uso"]["bono_entregas"] == 500
    assert data_bonus["resumen_uso"]["bono_paginas_ocr"] == 50
    assert data_bonus["resumen_uso"]["bono_minutos_voz"] == 120

    # Límite efectivo actualizado
    db_session.expire_all()
    suscriptor_actualizado = db_session.get(Suscriptor, suscriptor.id)
    assert suscriptor_actualizado.bono_entregas == 500
    limite_con_bono, _, _ = get_effective_entregas_limit(db_session, suscriptor_actualizado.id)
    assert limite_con_bono == (plan.max_entregas + 500)
