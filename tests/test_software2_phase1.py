# tests/test_software2_phase1.py
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.security import (
    create_access_token,
    create_refresh_token,
    rotate_refresh_token,
    revoke_refresh_token,
    require_permission,
    hash_password,
    hash_token
)
from app.models.refresh_token import RefreshToken
from app.models.administrador import Administrador
from app.models.catalogos import Rol, Permiso
from app.models.survey import CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta, PlantillaEncuesta
from app.services.queue_service import enqueue_channel_message, get_queue_metrics
from app.services.hash_chain_service import (
    calcular_hash_respuesta,
    vincular_hash_cadena,
    verificar_integridad_cadena,
    GENESIS_HASH
)

client = TestClient(app)

# ==============================================================================
# RF16: AUTENTICACIÓN OAUTH2/JWT CON RBAC, REFRESH TOKENS Y REVOCACIÓN
# ==============================================================================

def test_rf16_create_and_rotate_refresh_token(db_session: Session):
    user_id = uuid.uuid4()

    # 1. Crear refresh token
    raw_refresh = create_refresh_token(db_session, user_id)
    assert raw_refresh is not None
    assert len(raw_refresh) > 30

    token_hash = hash_token(raw_refresh)
    db_rec = db_session.query(RefreshToken).filter_by(token_hash=token_hash).first()
    assert db_rec is not None
    assert db_rec.revocado is False

    # 2. Rotar refresh token exitosamente
    old_rec, nuevo_raw_refresh = rotate_refresh_token(db_session, raw_refresh)
    assert old_rec.revocado is True
    assert nuevo_raw_refresh != raw_refresh

    # 3. Intentar reusar el refresh token revocado debe fallar con 401
    with pytest.raises(HTTPException) as exc_info:
        rotate_refresh_token(db_session, raw_refresh)
    assert exc_info.value.status_code == 401
    assert "revocado" in exc_info.value.detail.lower()

def test_rf16_revoke_refresh_token_logout(db_session: Session):
    user_id = uuid.uuid4()
    raw_refresh = create_refresh_token(db_session, user_id)

    # Revocar explícitamente (Logout)
    revocado = revoke_refresh_token(db_session, raw_refresh)
    assert revocado is True

    # El token revocado ya no puede refrescar
    with pytest.raises(HTTPException) as exc_info:
        rotate_refresh_token(db_session, raw_refresh)
    assert exc_info.value.status_code == 401

def test_rf16_require_permission_dependency(db_session: Session):
    from app.schemas.auth import TokenData

    # Asegurar que el rol operator exista en la BD para el test
    rol_op = db_session.query(Rol).filter_by(nombre="operator").first()
    if not rol_op:
        rol_op = Rol(nombre="operator", descripcion="Operador")
        db_session.add(rol_op)
        db_session.commit()

    # 1. Admin siempre pasa cualquier permiso
    admin_token = TokenData(sub=str(uuid.uuid4()), role="admin", permisos=[])
    dep_fn = require_permission("cualquier_permiso_arbitrario")
    res_admin = dep_fn(token_data=admin_token, db=db_session)
    assert res_admin == admin_token

    # 2. Usuario con permiso explícito en claims pasa
    operator_token = TokenData(sub=str(uuid.uuid4()), role="operator", permisos=["plantillas:ver"])
    dep_fn_plantilla = require_permission("plantillas:ver")
    res_operator = dep_fn_plantilla(token_data=operator_token, db=db_session)
    assert res_operator == operator_token

    # 3. Usuario sin permiso en claims ni en BD es rechazado con 403
    dep_fn_denegado = require_permission("super_secreto:eliminar")
    with pytest.raises(HTTPException) as exc_info:
        dep_fn_denegado(token_data=operator_token, db=db_session)
    assert exc_info.value.status_code == 403
    assert "Acceso denegado" in exc_info.value.detail

# ==============================================================================
# RF19: MOTOR DE INGESTA ASÍNCRONA MULTICANAL (REDIS / QUEUE)
# ==============================================================================

def test_rf19_ingesta_endpoint_immediate_202():
    payload = {
        "canal": "gmail",
        "contenido": "Excelente servicio, muy satisfecho con la atención",
        "tipo": "texto",
        "metadata": {"remitente": "cliente@test.com", "asunto": "Respuesta encuesta"}
    }
    response = client.post("/canales/ingesta", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["en_cola"] is True
    assert data["canal"] == "gmail"
    assert "task_id" in data

def test_rf19_ingesta_unsupported_channel():
    payload = {
        "canal": "canal_inexistente_xyz",
        "contenido": "Test",
        "tipo": "texto"
    }
    response = client.post("/canales/ingesta", json=payload)
    assert response.status_code == 400
    assert "Canal no soportado" in response.json()["detail"]

def test_rf19_queue_metrics():
    metrics = get_queue_metrics()
    assert "activo" in metrics
    assert "pendientes" in metrics
    assert "en_proceso" in metrics
    assert "fallidos" in metrics

# ==============================================================================
# RNF8: INTEGRIDAD DE DATOS MEDIANTE HASH-CHAIN CRIPTOGRÁFICO
# ==============================================================================

def test_rnf8_hash_chain_calculation():
    h1 = calcular_hash_respuesta({"respuesta": "si", "calificacion": 5}, GENESIS_HASH)
    assert len(h1) == 64
    assert h1 != GENESIS_HASH

    # Determinismo: Mismo contenido y mismo hash anterior produce idéntico hash
    h1_bis = calcular_hash_respuesta({"calificacion": 5, "respuesta": "si"}, GENESIS_HASH)
    assert h1 == h1_bis

    # Siguiente bloque en la cadena
    h2 = calcular_hash_respuesta({"respuesta": "no", "calificacion": 2}, h1)
    assert len(h2) == 64
    assert h2 != h1

def test_rnf8_hash_chain_verification_and_tampering_detection(db_session: Session):
    from app.models.suscriptor import Suscriptor
    suscriptor = Suscriptor(
        nombre="Empresa Hash Test",
        email=f"hash_{uuid.uuid4().hex[:8]}@test.com",
        password_hash="fake",
        rol_id=1
    )
    db_session.add(suscriptor)
    db_session.commit()

    plantilla = PlantillaEncuesta(
        suscriptor_id=suscriptor.id,
        nombre="Plantilla Test Hash Chain",
        descripcion="Test"
    )
    db_session.add(plantilla)
    db_session.commit()

    campana = CampanaEncuesta(
        suscriptor_id=suscriptor.id,
        plantilla_id=plantilla.id,
        nombre="Campaña Test Hash Chain",
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

    # Insertar 3 respuestas secuenciales vinculadas
    r1 = RespuestaEncuesta(
        entrega_id=entrega.id,
        raw_payload={"item": 1, "comentario": "Primero"},
        recibido_en=datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    db_session.add(r1)
    db_session.commit()
    vincular_hash_cadena(db_session, r1, campana.id)
    db_session.commit()

    r2 = RespuestaEncuesta(
        entrega_id=entrega.id,
        raw_payload={"item": 2, "comentario": "Segundo"},
        recibido_en=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    db_session.add(r2)
    db_session.commit()
    vincular_hash_cadena(db_session, r2, campana.id)
    db_session.commit()

    r3 = RespuestaEncuesta(
        entrega_id=entrega.id,
        raw_payload={"item": 3, "comentario": "Tercero"},
        recibido_en=datetime.now(timezone.utc)
    )
    db_session.add(r3)
    db_session.commit()
    vincular_hash_cadena(db_session, r3, campana.id)
    db_session.commit()

    # 1. Verificar cadena íntegra
    res_valida = verificar_integridad_cadena(db_session, campana.id)
    assert res_valida["integro"] is True
    assert res_valida["total_respuestas"] == 3
    assert len(res_valida["errores"]) == 0

    # 2. Simular alteración maliciosa en el contenido de la respuesta r2 sin recalcular
    r2.raw_payload = {"item": 2, "comentario": "Segundo ALTERADO MALICIOSAMENTE"}
    db_session.commit()

    res_corrupta = verificar_integridad_cadena(db_session, campana.id)
    assert res_corrupta["integro"] is False
    assert len(res_corrupta["errores"]) >= 1
    assert any(e["tipo_error"] == "CONTENIDO_MANIPULADO" for e in res_corrupta["errores"])
