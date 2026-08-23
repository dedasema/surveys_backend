import pytest
from uuid import uuid4
from app.models.suscriptor import Suscriptor
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.schemas.admin_suscriptores_schema import (
    SuscriptorListOut,
    SuscriptorDetail360Out,
    SuscriptorEstadoUpdate,
    SuscriptorAsignarPlan
)


def test_suscriptor_list_schema_validation():
    payload = {
        "id": str(uuid4()),
        "nombre_empresa": "Toyota Motors",
        "email_contacto": "admin@toyota.com",
        "telefono": "+59170000000",
        "estado": "activo",
        "creado_en": "2026-08-01T10:00:00Z",
        "plan": {
            "id": 2,
            "nombre": "Profesional",
            "precio_mensual": 49.99
        },
        "resumen_uso": {
            "plantillas_usadas": 4,
            "max_plantillas": 15,
            "campanas_activas": 2,
            "max_campanas": 10,
            "entregas_mes": 1250,
            "max_entregas": 5000,
            "operadores_activos": 2,
            "max_operadores": 5
        }
    }

    s_out = SuscriptorListOut(**payload)
    assert s_out.nombre_empresa == "Toyota Motors"
    assert s_out.plan.nombre == "Profesional"
    assert s_out.resumen_uso.entregas_mes == 1250


def test_suscriptor_estado_update_schema():
    up = SuscriptorEstadoUpdate(estado="suspendido")
    assert up.estado == "suspendido"


def test_suscriptor_asignar_plan_schema():
    ap = SuscriptorAsignarPlan(plan_id=3)
    assert ap.plan_id == 3
