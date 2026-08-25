"""
Domain Entities for Respuestas and Answers.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4


@dataclass
class RespuestaPregunta:
    pregunta_id: UUID
    id: UUID = field(default_factory=uuid4)
    texto: Optional[str] = None
    numero: Optional[Decimal] = None
    opcion_id: Optional[UUID] = None
    metadatos: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Respuesta:
    entrega_id: UUID
    id: UUID = field(default_factory=uuid4)
    recibido_en: Optional[datetime] = None
    puntuacion: Optional[Decimal] = None
    raw_payload: Optional[Dict[str, Any]] = None
    respuestas_preguntas: List[RespuestaPregunta] = field(default_factory=list)
