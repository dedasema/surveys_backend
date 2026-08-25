"""
Base Domain Exceptions.
These exceptions represent business rule violations independent of HTTP / Framework layers.
"""

class DomainError(Exception):
    """Base class for all domain errors."""
    def __init__(self, message: str = "A domain error occurred"):
        self.message = message
        super().__init__(self.message)


class EntityNotFoundError(DomainError):
    """Raised when a required domain entity cannot be found."""
    def __init__(self, entity_name: str, entity_id: any):
        self.entity_name = entity_name
        self.entity_id = entity_id
        super().__init__(f"{entity_name} with id '{entity_id}' was not found.")


class InvalidStateTransitionError(DomainError):
    """Raised when an illegal lifecycle state transition is attempted on an entity."""
    def __init__(self, entity_name: str, current_state: any, target_state: any, reason: str = ""):
        self.entity_name = entity_name
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason
        detail = f": {reason}" if reason else "."
        super().__init__(
            f"Invalid state transition for {entity_name} from '{current_state}' to '{target_state}'{detail}"
        )


class BusinessRuleViolationError(DomainError):
    """Raised when an operation violates a domain invariant or validation rule."""
    def __init__(self, message: str):
        super().__init__(message)


class UnauthorizedDomainActionError(DomainError):
    """Raised when a business action is disallowed for the current tenant or actor."""
    def __init__(self, message: str = "Unauthorized domain action"):
        super().__init__(message)
