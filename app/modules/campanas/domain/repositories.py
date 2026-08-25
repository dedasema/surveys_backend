"""
Repository Interface (Port) for Campana aggregate.
Decouples domain and application logic from any concrete persistence mechanism.
"""

from typing import List, Optional, Protocol
from uuid import UUID

from app.modules.campanas.domain.entities import Campana


class ICampanaRepository(Protocol):
    """Port for Campana persistence operations."""

    def get_by_id(self, campana_id: UUID) -> Optional[Campana]:
        """Fetch a single campaign by ID."""
        ...

    def list_by_suscriptor(self, suscriptor_id: UUID) -> List[Campana]:
        """List all campaigns belonging to a subscriber."""
        ...

    def list_programadas_pendientes(self) -> List[Campana]:
        """List all campaigns in PROGRAMADA state ready to be processed."""
        ...

    def save(self, campana: Campana) -> Campana:
        """Create or update a campaign."""
        ...

    def delete(self, campana_id: UUID) -> bool:
        """Delete a campaign by ID."""
        ...
