"""
Pure Domain Entities and Value Objects for Campanas.
Zero dependencies on FastAPI, SQLAlchemy, or external frameworks.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional
from uuid import UUID, uuid4

from app.modules.campanas.domain.exceptions import (
    CampanaInvalidTransitionError,
    CampanaValidationRuleError,
)


class EstadoCampanaEnum(IntEnum):
    BORRADOR = 1
    PROGRAMADA = 2
    ENVIADA = 3
    CERRADA = 4


TRANSICIONES_VALIDAS = {
    EstadoCampanaEnum.BORRADOR: [EstadoCampanaEnum.PROGRAMADA],
    EstadoCampanaEnum.PROGRAMADA: [EstadoCampanaEnum.ENVIADA, EstadoCampanaEnum.BORRADOR],
    EstadoCampanaEnum.ENVIADA: [EstadoCampanaEnum.CERRADA],
    EstadoCampanaEnum.CERRADA: [],
}


@dataclass
class Campana:
    suscriptor_id: UUID
    nombre: str
    canal_id: int
    id: UUID = field(default_factory=uuid4)
    descripcion: Optional[str] = None
    plantilla_id: Optional[UUID] = None
    estado_id: int = EstadoCampanaEnum.BORRADOR
    programada_en: Optional[datetime] = None
    creado_en: Optional[datetime] = None

    def __post_init__(self):
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        if not self.nombre or not self.nombre.strip():
            raise CampanaValidationRuleError("El nombre de la campaña no puede estar vacío.")
        if self.canal_id <= 0:
            raise CampanaValidationRuleError("El canal_id debe ser un identificador válido mayor a 0.")

    def validar_transicion(self, nuevo_estado: int) -> None:
        try:
            estado_actual_enum = EstadoCampanaEnum(self.estado_id)
            nuevo_estado_enum = EstadoCampanaEnum(nuevo_estado)
        except ValueError:
            raise CampanaInvalidTransitionError(
                self.estado_id, nuevo_estado, "Estado desconocido en el sistema"
            )

        permitidos = TRANSICIONES_VALIDAS.get(estado_actual_enum, [])
        if nuevo_estado_enum not in permitidos:
            raise CampanaInvalidTransitionError(
                self.estado_id,
                nuevo_estado,
                f"Transición no permitida de {estado_actual_enum.name} a {nuevo_estado_enum.name}",
            )

    def programar(self, fecha_programacion: datetime, plantilla_id: Optional[UUID] = None) -> None:
        self.validar_transicion(EstadoCampanaEnum.PROGRAMADA)
        
        target_plantilla = plantilla_id or self.plantilla_id
        if not target_plantilla:
            raise CampanaValidationRuleError("No se puede programar una campaña sin una plantilla asociada.")
        
        if not fecha_programacion:
            raise CampanaValidationRuleError("Se requiere una fecha válida para programar la campaña.")

        self.plantilla_id = target_plantilla
        self.programada_en = fecha_programacion
        self.estado_id = EstadoCampanaEnum.PROGRAMADA

    def marcar_como_enviada(self) -> None:
        self.validar_transicion(EstadoCampanaEnum.ENVIADA)
        self.estado_id = EstadoCampanaEnum.ENVIADA

    def cerrar(self) -> None:
        self.validar_transicion(EstadoCampanaEnum.CERRADA)
        self.estado_id = EstadoCampanaEnum.CERRADA

    def revertir_a_borrador(self) -> None:
        self.validar_transicion(EstadoCampanaEnum.BORRADOR)
        self.estado_id = EstadoCampanaEnum.BORRADOR

    def actualizar_datos_basicos(
        self,
        nombre: Optional[str] = None,
        descripcion: Optional[str] = None,
        plantilla_id: Optional[UUID] = None,
        canal_id: Optional[int] = None,
    ) -> None:
        if self.estado_id == EstadoCampanaEnum.CERRADA:
            raise CampanaValidationRuleError("No se puede modificar una campaña cerrada.")

        if nombre is not None:
            if not nombre.strip():
                raise CampanaValidationRuleError("El nombre no puede estar vacío.")
            self.nombre = nombre
        if descripcion is not None:
            self.descripcion = descripcion
        if plantilla_id is not None:
            self.plantilla_id = plantilla_id
        if canal_id is not None:
            if canal_id <= 0:
                raise CampanaValidationRuleError("El canal_id debe ser mayor a 0.")
            self.canal_id = canal_id
