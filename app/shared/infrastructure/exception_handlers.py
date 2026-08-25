"""
Global Exception Handlers for Domain Errors in FastAPI.
Maps pure business domain exceptions to standard HTTP response formats.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.shared.domain.exceptions import (
    DomainError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    BusinessRuleViolationError,
    UnauthorizedDomainActionError,
)


def register_domain_exception_handlers(app: FastAPI) -> None:
    """Registers exception handlers on the FastAPI app instance."""

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "error_type": "entity_not_found"},
        )

    @app.exception_handler(InvalidStateTransitionError)
    async def invalid_state_transition_handler(request: Request, exc: InvalidStateTransitionError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "error_type": "invalid_state_transition"},
        )

    @app.exception_handler(BusinessRuleViolationError)
    async def business_rule_violation_handler(request: Request, exc: BusinessRuleViolationError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "error_type": "business_rule_violation"},
        )

    @app.exception_handler(UnauthorizedDomainActionError)
    async def unauthorized_domain_action_handler(request: Request, exc: UnauthorizedDomainActionError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "error_type": "unauthorized_action"},
        )
