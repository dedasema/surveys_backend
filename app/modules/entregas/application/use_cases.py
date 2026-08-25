"""
Application Use Cases for Entregas and Destinatarios.
"""

from typing import List, Optional
from uuid import UUID

from app.modules.entregas.domain.entities import Entrega, Destinatario, EstadoEntregaEnum
from app.modules.entregas.domain.exceptions import EntregaNotFoundError, DestinatarioNotFoundError
from app.modules.entregas.domain.repositories import IEntregaRepository, IDestinatarioRepository


class CreateEntregaUseCase:
    def __init__(self, repo: IEntregaRepository):
        self.repo = repo

    def execute(self, campana_id: UUID, canal_id: int, destinatario_id: Optional[UUID] = None) -> Entrega:
        entrega = Entrega(
            campana_id=campana_id,
            canal_id=canal_id,
            destinatario_id=destinatario_id,
            estado_id=EstadoEntregaEnum.PENDIENTE,
        )
        return self.repo.save(entrega)


class CreateBulkEntregasUseCase:
    def __init__(self, repo: IEntregaRepository):
        self.repo = repo

    def execute(self, campana_id: UUID, canal_id: int, destinatario_ids: List[UUID]) -> List[Entrega]:
        entregas = [
            Entrega(
                campana_id=campana_id,
                canal_id=canal_id,
                destinatario_id=d_id,
                estado_id=EstadoEntregaEnum.PENDIENTE,
            )
            for d_id in destinatario_ids
        ]
        return self.repo.save_bulk(entregas)


class CreateDestinatarioUseCase:
    def __init__(self, repo: IDestinatarioRepository):
        self.repo = repo

    def execute(self, suscriptor_id: UUID, nombre: str, email: Optional[str] = None, telefono: Optional[str] = None) -> Destinatario:
        destinatario = Destinatario(
            suscriptor_id=suscriptor_id,
            nombre=nombre,
            email=email,
            telefono=telefono,
        )
        return self.repo.save(destinatario)


class ListDestinatariosUseCase:
    def __init__(self, repo: IDestinatarioRepository):
        self.repo = repo

    def execute(self, suscriptor_id: UUID) -> List[Destinatario]:
        return self.repo.list_by_suscriptor(suscriptor_id)
