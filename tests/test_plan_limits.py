import pytest
from uuid import uuid4
from fastapi import HTTPException
from app.schemas.subscription import PlanSuscripcionCreate
from app.models.subscription import PlanSuscripcion
from app.services.plan_limits_service import (
    get_plan_suscriptor,
    validate_plantillas_limit,
    validate_campanas_limit,
    validate_operadores_limit,
    validate_canal_permission
)


def test_plan_suscripcion_schema_defaults():
    plan_data = PlanSuscripcionCreate(
        nombre="Plan Test",
        precio_mensual=10.00
    )
    assert plan_data.max_plantillas == 5
    assert plan_data.max_campanas == 5
    assert plan_data.max_entregas == 500
    assert plan_data.max_operadores == 1
    assert plan_data.permite_email is True
    assert plan_data.permite_audio_voz is False
    assert plan_data.permite_papel is False


def test_get_plan_suscriptor_fallback(db_session):
    dummy_suscriptor_id = uuid4()
    plan = get_plan_suscriptor(db_session, dummy_suscriptor_id)
    assert plan is not None
    assert plan.max_plantillas > 0


def test_validate_canal_permission_gratuito(db_session):
    dummy_suscriptor_id = uuid4()
    
    # Canal 1 (email), Canal 4 (papel) y Canal 5 (audio/voz) permitidos en Gratuito para demo
    validate_canal_permission(db_session, dummy_suscriptor_id, 1)
    validate_canal_permission(db_session, dummy_suscriptor_id, 4)
    validate_canal_permission(db_session, dummy_suscriptor_id, 5)
