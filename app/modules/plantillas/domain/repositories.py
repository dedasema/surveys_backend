"""
Repository interfaces (Ports) for Plantilla, Pregunta, and Opcion aggregates.
"""

from typing import List, Optional, Protocol
from uuid import UUID

from app.modules.plantillas.domain.entities import Plantilla, Pregunta, Opcion


class IPlantillaRepository(Protocol):
    def get_by_id(self, plantilla_id: UUID) -> Optional[Plantilla]:
        ...

    def get_con_preguntas(self, plantilla_id: UUID) -> Optional[Plantilla]:
        ...

    def list_by_suscriptor(self, suscriptor_id: UUID) -> List[Plantilla]:
        ...

    def save(self, plantilla: Plantilla) -> Plantilla:
        ...

    def delete(self, plantilla_id: UUID) -> bool:
        ...


class IPreguntaRepository(Protocol):
    def get_by_id(self, pregunta_id: UUID) -> Optional[Pregunta]:
        ...

    def list_by_plantilla(self, plantilla_id: UUID) -> List[Pregunta]:
        ...

    def save(self, pregunta: Pregunta) -> Pregunta:
        ...

    def delete(self, pregunta_id: UUID) -> bool:
        ...


class IOpcionRepository(Protocol):
    def get_by_id(self, opcion_id: UUID) -> Optional[Opcion]:
        ...

    def list_by_pregunta(self, pregunta_id: UUID) -> List[Opcion]:
        ...

    def save(self, opcion: Opcion) -> Opcion:
        ...

    def delete(self, opcion_id: UUID) -> bool:
        ...
