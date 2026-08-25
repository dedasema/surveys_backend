"""
Domain Entities for Subscription Plans and Quotas.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.modules.subscription.domain.exceptions import PlanLimitExceededError, ChannelNotAllowedError


@dataclass
class Plan:
    id: int
    nombre: str
    precio_mensual: Decimal
    max_plantillas: int = 5
    max_campanas: int = 5
    max_entregas: int = 500
    max_operadores: int = 1
    permite_email: bool = True
    permite_audio_voz: bool = False
    permite_papel: bool = False
    descripcion: Optional[str] = None

    def validar_limite_plantillas(self, actual: int) -> None:
        if self.max_plantillas > 0 and actual >= self.max_plantillas:
            raise PlanLimitExceededError("Plantillas", self.max_plantillas, actual)

    def validar_limite_campanas(self, actual: int) -> None:
        if self.max_campanas > 0 and actual >= self.max_campanas:
            raise PlanLimitExceededError("Campañas", self.max_campanas, actual)

    def validar_limite_operadores(self, actual: int) -> None:
        if self.max_operadores > 0 and actual >= self.max_operadores:
            raise PlanLimitExceededError("Operadores", self.max_operadores, actual)

    def validar_canal_permitido(self, canal_id: int) -> None:
        # Canal 1: Email, Canal 4: Papel/QR, Canal 5: Audio/Voz
        if canal_id == 5 and not self.permite_audio_voz:
            raise ChannelNotAllowedError("Audio/Voz", self.nombre)
        if canal_id == 4 and not self.permite_papel:
            raise ChannelNotAllowedError("Papel/QR", self.nombre)
        if canal_id == 1 and not self.permite_email:
            raise ChannelNotAllowedError("Email", self.nombre)
