"""
Domain Exceptions for Subscriptions and Plan Limits.
"""

from app.shared.domain.exceptions import BusinessRuleViolationError


class PlanLimitExceededError(BusinessRuleViolationError):
    def __init__(self, resource_name: str, limit: int, current_count: int):
        super().__init__(
            f"Límite de plan excedido para '{resource_name}'. Límite: {limit}, actual: {current_count}."
        )


class ChannelNotAllowedError(BusinessRuleViolationError):
    def __init__(self, canal_nombre: str, plan_nombre: str):
        super().__init__(
            f"El canal '{canal_nombre}' no está disponible en el plan '{plan_nombre}'. Actualiza tu suscripción."
        )
