import pytest
from uuid import uuid4
from decimal import Decimal
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor, PagoSuscriptor
from app.schemas.subscription import MembresiaActualOut, PagoSuscriptorOut, PortalClienteOut


def test_membresia_actual_schema_structure():
    plan_data = {
        "id": 2,
        "nombre": "Profesional",
        "precio_mensual": Decimal("49.99"),
        "descripcion": "Plan Pro",
        "max_plantillas": 15,
        "max_campanas": 10,
        "max_entregas": 5000,
        "max_operadores": 5,
        "permite_email": True,
        "permite_audio_voz": True,
        "permite_papel": True,
        "permite_ia_analisis": True,
        "permite_exportacion": True,
        "creado_en": "2026-08-01T00:00:00Z"
    }

    payload = {
        "id": str(uuid4()),
        "estado": "activa",
        "fecha_inicio": "2026-08-01T00:00:00Z",
        "fecha_fin": "2026-09-01T00:00:00Z",
        "dias_restantes": 9,
        "renovacion_automatica": True,
        "plan": plan_data,
        "uso_actual": {
            "plantillas_usadas": 4,
            "campanas_activas": 2,
            "entregas_mes_actual": 1250,
            "operadores_activos": 2
        }
    }

    membresia = MembresiaActualOut(**payload)
    assert membresia.estado == "activa"
    assert membresia.plan.nombre == "Profesional"
    assert membresia.uso_actual.plantillas_usadas == 4
    assert membresia.uso_actual.entregas_mes_actual == 1250


def test_pago_suscriptor_schema():
    pago_data = {
        "id": str(uuid4()),
        "referencia_stripe": "pi_3MXXXXXXXXXXXX",
        "monto": Decimal("49.99"),
        "moneda": "usd",
        "fecha": "2026-08-01T14:20:00Z",
        "plan_nombre": "Profesional",
        "metodo_pago": "Tarjeta de Crédito / Débito",
        "estado": "completado",
        "recibo_url": "https://pay.stripe.com/receipts/test"
    }

    pago = PagoSuscriptorOut(**pago_data)
    assert pago.plan_nombre == "Profesional"
    assert pago.monto == Decimal("49.99")
