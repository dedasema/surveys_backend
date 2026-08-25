"""
Domain Exceptions for Respuestas and Public Survey Submissions.
"""

from uuid import UUID
from app.shared.domain.exceptions import EntityNotFoundError, BusinessRuleViolationError


class RespuestaNotFoundError(EntityNotFoundError):
    def __init__(self, respuesta_id: UUID):
        super().__init__(entity_name="Respuesta", entity_id=str(respuesta_id))


class RespuestaValidationRuleError(BusinessRuleViolationError):
    def __init__(self, message: str):
        super().__init__(message)
