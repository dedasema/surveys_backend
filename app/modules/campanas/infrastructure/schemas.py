"""
HTTP Request and Response Schemas for the Campanas module.
Re-exports and wraps DTOs for FastAPI controllers.
"""

from app.schemas.campanas_schema import (
    CampanaBase,
    CampanaCreate,
    CampanaUpdate,
    CampanaOut,
    CampanaDetailOut,
    CampanaFullDetailOut,
    PlantillaInResponse,
    EntregaInResponse,
    RespuestaInResponse,
    DestinatarioInResponse,
)

__all__ = [
    "CampanaBase",
    "CampanaCreate",
    "CampanaUpdate",
    "CampanaOut",
    "CampanaDetailOut",
    "CampanaFullDetailOut",
    "PlantillaInResponse",
    "EntregaInResponse",
    "RespuestaInResponse",
    "DestinatarioInResponse",
]
