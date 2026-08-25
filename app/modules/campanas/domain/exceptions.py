"""
Domain exceptions for the Campanas module.
"""

from uuid import UUID
from app.shared.domain.exceptions import EntityNotFoundError, InvalidStateTransitionError, BusinessRuleViolationError


class CampanaNotFoundError(EntityNotFoundError):
    def __init__(self, campana_id: UUID):
        super().__init__(entity_name="Campaña", entity_id=str(campana_id))


class CampanaInvalidTransitionError(InvalidStateTransitionError):
    def __init__(self, current_state: int, target_state: int, reason: str = ""):
        super().__init__(
            entity_name="Campaña",
            current_state=current_state,
            target_state=target_state,
            reason=reason,
        )


class CampanaValidationRuleError(BusinessRuleViolationError):
    def __init__(self, message: str):
        super().__init__(message)
