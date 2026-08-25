"""
Domain Exceptions for Entregas and Destinatarios.
"""

from uuid import UUID
from app.shared.domain.exceptions import EntityNotFoundError, BusinessRuleViolationError, InvalidStateTransitionError


class EntregaNotFoundError(EntityNotFoundError):
    def __init__(self, entrega_id: UUID):
        super().__init__(entity_name="Entrega", entity_id=str(entrega_id))


class DestinatarioNotFoundError(EntityNotFoundError):
    def __init__(self, destinatario_id: UUID):
        super().__init__(entity_name="Destinatario", entity_id=str(destinatario_id))


class EntregaInvalidTransitionError(InvalidStateTransitionError):
    def __init__(self, current_state: int, target_state: int, reason: str = ""):
        super().__init__(
            entity_name="Entrega",
            current_state=current_state,
            target_state=target_state,
            reason=reason,
        )


class EntregaDomainError(BusinessRuleViolationError):
    def __init__(self, message: str):
        super().__init__(message)
