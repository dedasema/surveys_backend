"""
Application Layer DTOs (Data Transfer Objects) for Campanas.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class CreateCampanaCommand:
    suscriptor_id: UUID
    nombre: str
    canal_id: int
    descripcion: Optional[str] = None
    plantilla_id: Optional[UUID] = None
    programada_en: Optional[datetime] = None


@dataclass
class UpdateCampanaCommand:
    campana_id: UUID
    suscriptor_id: UUID
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    plantilla_id: Optional[UUID] = None
    canal_id: Optional[int] = None
    estado_id: Optional[int] = None
    programada_en: Optional[datetime] = None
