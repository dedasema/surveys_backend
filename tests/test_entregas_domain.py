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
