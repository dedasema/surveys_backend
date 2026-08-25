"""
Unit tests for Subscription Plan domain entity and quota invariants.
"""

from decimal import Decimal
import pytest

from app.modules.subscription.domain.entities import Plan
from app.modules.subscription.domain.exceptions import PlanLimitExceededError, ChannelNotAllowedError


def test_plan_quota_validation():
    plan = Plan(
        id=1,
        nombre="Gratuito",
        precio_mensual=Decimal("0.0"),
        max_plantillas=3,
        max_campanas=2,
        permite_audio_voz=False,
    )

    # Validar cuota plantillas
    plan.validar_limite_plantillas(2)  # OK
    with pytest.raises(PlanLimitExceededError, match="Plantillas"):
        plan.validar_limite_plantillas(3)

    # Validar canal restringido
    with pytest.raises(ChannelNotAllowedError, match="Audio/Voz"):
        plan.validar_canal_permitido(5)
