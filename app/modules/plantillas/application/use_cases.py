"""
Application use cases for Plantillas, Preguntas, and Opciones.
"""

from typing import List, Optional
from uuid import UUID

from app.modules.plantillas.domain.entities import Plantilla, Pregunta, Opcion
from app.modules.plantillas.domain.exceptions import (
    PlantillaNotFoundError,
    PreguntaNotFoundError,
    OpcionNotFoundError,
)
from app.modules.plantillas.domain.repositories import (
    IPlantillaRepository,
    IPreguntaRepository,
    IOpcionRepository,
)


class CreatePlantillaUseCase:
    def __init__(self, repo: IPlantillaRepository):
        self.repo = repo

    def execute(self, suscriptor_id: UUID, nombre: str, descripcion: Optional[str] = None) -> Plantilla:
        plantilla = Plantilla(
            suscriptor_id=suscriptor_id,
            nombre=nombre,
            descripcion=descripcion,
        )
        return self.repo.save(plantilla)


class GetPlantillaUseCase:
    def __init__(self, repo: IPlantillaRepository):
        self.repo = repo

    def execute(self, plantilla_id: UUID, con_preguntas: bool = False) -> Plantilla:
        plantilla = (
            self.repo.get_con_preguntas(plantilla_id)
            if con_preguntas
            else self.repo.get_by_id(plantilla_id)
        )
        if not plantilla:
            raise PlantillaNotFoundError(plantilla_id)
        return plantilla


class ListPlantillasUseCase:
    def __init__(self, repo: IPlantillaRepository):
        self.repo = repo

    def execute(self, suscriptor_id: UUID) -> List[Plantilla]:
        return self.repo.list_by_suscriptor(suscriptor_id)


class UpdatePlantillaUseCase:
    def __init__(self, repo: IPlantillaRepository):
        self.repo = repo

    def execute(self, plantilla_id: UUID, nombre: Optional[str] = None, descripcion: Optional[str] = None) -> Plantilla:
        plantilla = self.repo.get_by_id(plantilla_id)
        if not plantilla:
            raise PlantillaNotFoundError(plantilla_id)
        plantilla.actualizar(nombre=nombre, descripcion=descripcion)
        return self.repo.save(plantilla)


class DeletePlantillaUseCase:
    def __init__(self, repo: IPlantillaRepository):
        self.repo = repo

    def execute(self, plantilla_id: UUID) -> bool:
        plantilla = self.repo.get_by_id(plantilla_id)
        if not plantilla:
            raise PlantillaNotFoundError(plantilla_id)
        return self.repo.delete(plantilla_id)
