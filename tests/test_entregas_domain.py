"""
Unit tests for Entrega and Destinatario Domain Entities.
Tests state transitions and contact validation in memory.
"""

from uuid import uuid4
import pytest

from app.modules.entregas.domain.entities import Entrega, Destinatario, EstadoEntregaEnum
from app.modules.entregas.domain.exceptions import EntregaDomainError, EntregaInvalidTransitionError


def test_create_destinatario_with_email():
    dest = Destinatario(
        suscriptor_id=uuid4(),
        nombre="Juan Pérez",
        email="juan@empresa.com",
    )
    assert dest.nombre == "Juan Pérez"
    assert dest.email == "juan@empresa.com"
    assert dest.telefono is None


def test_destinatario_requires_contact_info():
    with pytest.raises(EntregaDomainError, match="debe tener al menos un email o teléfono"):
        Destinatario(
            suscriptor_id=uuid4(),
            nombre="Sin Contacto",
            email=None,
            telefono=None,
        )


def test_entrega_lifecycle_transitions():
    entrega = Entrega(
        campana_id=uuid4(),
        canal_id=1,
    )
    assert entrega.estado_id == EstadoEntregaEnum.PENDIENTE

    # 1. Marcar como enviado
    entrega.marcar_como_enviado()
    assert entrega.estado_id == EstadoEntregaEnum.ENVIADO
    assert entrega.enviado_en is not None

    # 2. Marcar como respondido
    entrega.marcar_como_respondido()
    assert entrega.estado_id == EstadoEntregaEnum.RESPONDIDO
    assert entrega.respondido_en is not None

    # 3. Intentar volver a enviado tras respondido falla
    with pytest.raises(EntregaInvalidTransitionError):
        entrega.marcar_como_enviado()


def test_entrega_detail_out_schema_with_orm_models():
    """Ensure EntregaDetailOut correctly serializes nested ORM-like response models."""
    from datetime import datetime, timezone
    from app.schemas.entregas_schema import EntregaDetailOut

    class DummyRespuestaPregunta:
        def __init__(self):
            self.id = uuid4()
            self.pregunta_id = uuid4()
            self.texto = "Excelente servicio"
            self.numero = 9.5
            self.opcion_id = None
            self.metadatos = {"canal": "web"}

    class DummyRespuesta:
        def __init__(self):
            self.id = uuid4()
            self.entrega_id = uuid4()
            self.recibido_en = datetime.now(timezone.utc)
            self.puntuacion = 10.0
            self.raw_payload = {"source": "mobile"}
            self.respuestas_preguntas = [DummyRespuestaPregunta()]

    class DummyEntrega:
        def __init__(self):
            self.id = uuid4()
            self.campana_id = uuid4()
            self.canal_id = 1
            self.destinatario_id = None
            self.estado_id = 3
            self.enviado_en = datetime.now(timezone.utc)
            self.respondido_en = datetime.now(timezone.utc)
            self.destinatario = None
            self.consentimiento_aceptado = True
            self.consentimiento_en = datetime.now(timezone.utc)
            self.respuestas = [DummyRespuesta()]

    dummy = DummyEntrega()
    out = EntregaDetailOut.model_validate(dummy)
    assert out.id == dummy.id
    assert len(out.respuestas) == 1
    assert out.respuestas[0].respuestas_preguntas[0].texto == "Excelente servicio"
    assert out.consentimiento_aceptado is True
