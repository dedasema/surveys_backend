"""
Domain Entities for Entregas and Destinatarios.
Pure Python representation with lifecycle methods and invariants.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional
from uuid import UUID, uuid4

from app.modules.entregas.domain.exceptions import (
    EntregaDomainError,
    EntregaInvalidTransitionError,
)


class EstadoEntregaEnum(IntEnum):
    PENDIENTE = 1
    ENVIADO = 2
    ENTREGADO = 3
    ABIERTO = 4
    RESPONDIDO = 5
    FALLIDO = 6
    REBOTADO = 7


@dataclass
class Destinatario:
    suscriptor_id: UUID
    nombre: str
    id: UUID = field(default_factory=uuid4)
    email: Optional[str] = None
    telefono: Optional[str] = None
    creado_en: Optional[datetime] = None

    def __post_init__(self):
        if not self.nombre or not self.nombre.strip():
            raise EntregaDomainError("El nombre del destinatario no puede estar vacío.")
        if not self.email and not self.telefono:
            raise EntregaDomainError("El destinatario debe tener al menos un email o teléfono de contacto.")


@dataclass
class Entrega:
    campana_id: UUID
    canal_id: int
    id: UUID = field(default_factory=uuid4)
    destinatario_id: Optional[UUID] = None
    estado_id: int = EstadoEntregaEnum.PENDIENTE
    enviado_en: Optional[datetime] = None
    respondido_en: Optional[datetime] = None

    def marcar_como_enviado(self, fecha: Optional[datetime] = None) -> None:
        if self.estado_id == EstadoEntregaEnum.RESPONDIDO:
            raise EntregaInvalidTransitionError(
                self.estado_id, EstadoEntregaEnum.ENVIADO, "Una entrega ya respondida no puede volver a marcarse como enviada."
            )
        self.estado_id = EstadoEntregaEnum.ENVIADO
        self.enviado_en = fecha or datetime.now(timezone.utc)

    def marcar_como_respondido(self, fecha: Optional[datetime] = None) -> None:
        if self.estado_id == EstadoEntregaEnum.RESPONDIDO:
            return  # Idempotente
        self.estado_id = EstadoEntregaEnum.RESPONDIDO
        self.respondido_en = fecha or datetime.now(timezone.utc)

    def marcar_como_fallido(self) -> None:
        if self.estado_id == EstadoEntregaEnum.RESPONDIDO:
            raise EntregaInvalidTransitionError(
                self.estado_id, EstadoEntregaEnum.FALLIDO, "No se puede marcar como fallida una entrega ya respondida."
            )
        self.estado_id = EstadoEntregaEnum.FALLIDO
