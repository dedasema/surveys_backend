"""
Repository Interfaces (Ports) for Entregas and Destinatarios.
"""

from typing import List, Optional, Protocol
from uuid import UUID

from app.modules.entregas.domain.entities import Entrega, Destinatario


class IEntregaRepository(Protocol):
    def get_by_id(self, entrega_id: UUID) -> Optional[Entrega]:
        ...

    def list_by_campana(self, campana_id: UUID) -> List[Entrega]:
        ...

    def save(self, entrega: Entrega) -> Entrega:
        ...

    def save_bulk(self, entregas: List[Entrega]) -> List[Entrega]:
        ...

    def delete(self, entrega_id: UUID) -> bool:
        ...


class IDestinatarioRepository(Protocol):
    def get_by_id(self, destinatario_id: UUID) -> Optional[Destinatario]:
        ...

    def list_by_suscriptor(self, suscriptor_id: UUID) -> List[Destinatario]:
        ...

    def save(self, destinatario: Destinatario) -> Destinatario:
        ...

    def delete(self, destinatario_id: UUID) -> bool:
        ...
