"""
Domain Exceptions for the Plantillas (Survey Builder) module.
"""

from uuid import UUID
from app.shared.domain.exceptions import EntityNotFoundError, BusinessRuleViolationError


class PlantillaNotFoundError(EntityNotFoundError):
    def __init__(self, plantilla_id: UUID):
        super().__init__(entity_name="Plantilla", entity_id=str(plantilla_id))


class PreguntaNotFoundError(EntityNotFoundError):
    def __init__(self, pregunta_id: UUID):
        super().__init__(entity_name="Pregunta", entity_id=str(pregunta_id))


class OpcionNotFoundError(EntityNotFoundError):
    def __init__(self, opcion_id: UUID):
        super().__init__(entity_name="Opción", entity_id=str(opcion_id))


class PlantillaDomainError(BusinessRuleViolationError):
    def __init__(self, message: str):
        super().__init__(message)
