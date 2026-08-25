"""
Unit Tests for Campana Pure Domain Entity.
Tests state transitions, invariants, and business rules in memory without any DB dependency.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest

from app.modules.campanas.domain.entities import Campana, EstadoCampanaEnum
from app.modules.campanas.domain.exceptions import (
    CampanaInvalidTransitionError,
    CampanaValidationRuleError,
)


def test_create_campana_in_borrador_state():
    suscriptor_id = uuid4()
    campana = Campana(
        suscriptor_id=suscriptor_id,
        nombre="Encuesta de Satisfacción Q3",
        canal_id=1,
    )

    assert campana.estado_id == EstadoCampanaEnum.BORRADOR
    assert campana.nombre == "Encuesta de Satisfacción Q3"
    assert campana.plantilla_id is None
    assert campana.programada_en is None


def test_cannot_create_campana_with_empty_name():
    with pytest.raises(CampanaValidationRuleError, match="El nombre de la campaña no puede estar vacío"):
        Campana(
            suscriptor_id=uuid4(),
            nombre="   ",
            canal_id=1,
        )


def test_cannot_create_campana_with_invalid_canal():
    with pytest.raises(CampanaValidationRuleError, match="canal_id debe ser un identificador válido"):
        Campana(
            suscriptor_id=uuid4(),
            nombre="Campaña Válida",
            canal_id=0,
        )


def test_programar_campana_success():
    campana = Campana(
        suscriptor_id=uuid4(),
        nombre="Campaña Black Friday",
        canal_id=1,
    )
    plantilla_id = uuid4()
    fecha_futura = datetime.now(timezone.utc) + timedelta(days=2)

    campana.programar(fecha_programacion=fecha_futura, plantilla_id=plantilla_id)

    assert campana.estado_id == EstadoCampanaEnum.PROGRAMADA
    assert campana.plantilla_id == plantilla_id
    assert campana.programada_en == fecha_futura


def test_cannot_program_without_plantilla():
    campana = Campana(
        suscriptor_id=uuid4(),
        nombre="Campaña sin plantilla",
        canal_id=1,
    )
    fecha_futura = datetime.now(timezone.utc) + timedelta(days=1)

    with pytest.raises(CampanaValidationRuleError, match="No se puede programar una campaña sin una plantilla"):
        campana.programar(fecha_programacion=fecha_futura, plantilla_id=None)


def test_invalid_lifecycle_transition_raises_domain_error():
    campana = Campana(
        suscriptor_id=uuid4(),
        nombre="Campaña Directa",
        canal_id=1,
    )
    # Intentar pasar de BORRADOR directamente a ENVIADA o CERRADA no está permitido
    with pytest.raises(CampanaInvalidTransitionError):
        campana.cerrar()

    with pytest.raises(CampanaInvalidTransitionError):
        campana.marcar_como_enviada()


def test_complete_lifecycle_flow():
    campana = Campana(
        suscriptor_id=uuid4(),
        nombre="Campaña Ciclo Completo",
        canal_id=1,
    )
    plantilla_id = uuid4()
    fecha = datetime.now(timezone.utc) + timedelta(hours=1)

    # 1. Borrador -> Programada
    campana.programar(fecha_programacion=fecha, plantilla_id=plantilla_id)
    assert campana.estado_id == EstadoCampanaEnum.PROGRAMADA

    # 2. Programada -> Enviada
    campana.marcar_como_enviada()
    assert campana.estado_id == EstadoCampanaEnum.ENVIADA

    # 3. Enviada -> Cerrada
    campana.cerrar()
    assert campana.estado_id == EstadoCampanaEnum.CERRADA

    # 4. Cerrada -> No permite más modificaciones
    with pytest.raises(CampanaValidationRuleError, match="No se puede modificar una campaña cerrada"):
        campana.actualizar_datos_basicos(nombre="Nuevo Nombre")
