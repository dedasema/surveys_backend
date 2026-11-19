from datetime import datetime
from typing import Optional, List, Union, Any, Dict
from uuid import UUID

from pydantic import BaseModel


# ───────── modelos auxiliares ────────────────────────────────────────────
class OpcionPublicaOut(BaseModel):
    id: UUID
    texto: str
    valor: Optional[str] = None

    model_config = {"from_attributes": True}


class PreguntaPublicaOut(BaseModel):
    id: UUID
    orden: int
    texto: str
    tipo_pregunta_id: int
    obligatorio: bool
    opciones: List[OpcionPublicaOut] = []

    model_config = {"from_attributes": True}


class PlantillaPublicaOut(BaseModel):
    id: UUID
    nombre: str
    descripcion: Optional[str] = None
    preguntas: List[PreguntaPublicaOut] = []

    model_config = {"from_attributes": True}


# ───────── destinatario (todo opcional) ──────────────────────────────────
class DestinatarioPublicoOut(BaseModel):
    id: Optional[UUID] = None        # ← añadido id opcional (por consistencia)
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None

    model_config = {"from_attributes": True}


# ───────── entrega “pública” ─────────────────────────────────────────────
class EntregaPublicaOut(BaseModel):
    id: UUID
    plantilla: PlantillaPublicaOut
    destinatario: Optional[DestinatarioPublicoOut] = None   # ← opcional

    model_config = {"from_attributes": True}


# ───────── CRUD privado de entregas ──────────────────────────────────────
class EntregaBase(BaseModel):
    destinatario_id: Optional[UUID] = None
    canal_id: int


class EntregaCreate(EntregaBase):
    pass


class EntregaUpdate(BaseModel):
    estado_id: Optional[int] = None
    enviado_en: Optional[datetime] = None
    respondido_en: Optional[datetime] = None


class EntregaOut(EntregaBase):
    id: UUID
    campana_id: UUID
    estado_id: int
    enviado_en: Optional[datetime] = None
    respondido_en: Optional[datetime] = None
    destinatario: Optional[DestinatarioPublicoOut] = None   # ← añadido
    consentimiento_aceptado: Optional[bool] = False
    consentimiento_en: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RespuestaPreguntaDetailOut(BaseModel):
    id: UUID
    pregunta_id: UUID
    texto: Optional[str] = None
    numero: Optional[float] = None
    opcion_id: Optional[UUID] = None
    metadatos: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class RespuestaEntregaDetailOut(BaseModel):
    id: UUID
    entrega_id: UUID
    recibido_en: Optional[datetime] = None
    puntuacion: Optional[float] = None
    raw_payload: Optional[Dict[str, Any]] = None
    respuestas_preguntas: List[RespuestaPreguntaDetailOut] = []

    model_config = {"from_attributes": True}


class EntregaDetailOut(EntregaOut):
    respuestas: List[Union[RespuestaEntregaDetailOut, Dict[str, Any]]] = []

    model_config = {"from_attributes": True}
