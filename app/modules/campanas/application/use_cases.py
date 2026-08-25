"""
Application Use Cases for Campanas.
Coordinates domain entities and repository ports to fulfill business operations.
"""

from typing import List, Optional
from uuid import UUID

from app.modules.campanas.application.dtos import CreateCampanaCommand, UpdateCampanaCommand
from app.modules.campanas.domain.entities import Campana, EstadoCampanaEnum
from app.modules.campanas.domain.exceptions import CampanaNotFoundError
from app.modules.campanas.domain.repositories import ICampanaRepository


class CreateCampanaUseCase:
    def __init__(self, repository: ICampanaRepository):
        self.repository = repository

    def execute(self, command: CreateCampanaCommand) -> Campana:
        campana = Campana(
            suscriptor_id=command.suscriptor_id,
            nombre=command.nombre,
            canal_id=command.canal_id,
            descripcion=command.descripcion,
            plantilla_id=command.plantilla_id,
            programada_en=command.programada_en,
            estado_id=EstadoCampanaEnum.BORRADOR,
        )
        return self.repository.save(campana)


class GetCampanaUseCase:
    def __init__(self, repository: ICampanaRepository):
        self.repository = repository

    def execute(self, campana_id: UUID) -> Campana:
        campana = self.repository.get_by_id(campana_id)
        if not campana:
            raise CampanaNotFoundError(campana_id)
        return campana


class ListCampanasUseCase:
    def __init__(self, repository: ICampanaRepository):
        self.repository = repository

    def execute(self, suscriptor_id: UUID) -> List[Campana]:
        return self.repository.list_by_suscriptor(suscriptor_id)


class UpdateCampanaUseCase:
    def __init__(self, repository: ICampanaRepository):
        self.repository = repository

    def execute(self, command: UpdateCampanaCommand) -> Campana:
        campana = self.repository.get_by_id(command.campana_id)
        if not campana:
            raise CampanaNotFoundError(command.campana_id)

        # 1. Update basic fields if provided
        campana.actualizar_datos_basicos(
            nombre=command.nombre,
            descripcion=command.descripcion,
            plantilla_id=command.plantilla_id,
            canal_id=command.canal_id,
        )

        # 2. Handle state transitions using domain methods
        if command.estado_id is not None and command.estado_id != campana.estado_id:
            if command.estado_id == EstadoCampanaEnum.PROGRAMADA:
                fecha = command.programada_en or campana.programada_en
                plantilla = command.plantilla_id or campana.plantilla_id
                campana.programar(fecha_programacion=fecha, plantilla_id=plantilla)
            elif command.estado_id == EstadoCampanaEnum.ENVIADA:
                campana.marcar_como_enviada()
            elif command.estado_id == EstadoCampanaEnum.CERRADA:
                campana.cerrar()
            elif command.estado_id == EstadoCampanaEnum.BORRADOR:
                campana.revertir_a_borrador()
            else:
                campana.validar_transicion(command.estado_id)
                campana.estado_id = command.estado_id

        # 3. Update scheduled date if provided without state change
        if command.programada_en is not None:
            campana.programada_en = command.programada_en

        return self.repository.save(campana)


class DeleteCampanaUseCase:
    def __init__(self, repository: ICampanaRepository):
        self.repository = repository

    def execute(self, campana_id: UUID) -> bool:
        campana = self.repository.get_by_id(campana_id)
        if not campana:
            raise CampanaNotFoundError(campana_id)
        return self.repository.delete(campana_id)
