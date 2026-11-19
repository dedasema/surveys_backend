from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel
from decimal import Decimal


class RespuestaPreguntaBase(BaseModel):
    pregunta_id: UUID
    texto: Optional[str] = None
    numero: Optional[Decimal] = None
    opcion_id: Optional[UUID] = None
    metadatos: dict = {}


class RespuestaPreguntaCreate(RespuestaPreguntaBase):
    pass


class RespuestaPreguntaOut(RespuestaPreguntaBase):
    id: UUID
    respuesta_id: UUID

    model_config = {"from_attributes": True}


class RespuestaEncuestaBase(BaseModel):
    raw_payload: Optional[dict] = None


class RespuestaEncuestaCreate(RespuestaEncuestaBase):
    respuestas_preguntas: List[RespuestaPreguntaCreate]
    consentimiento_aceptado: Optional[bool] = None


class RespuestaEncuestaUpdate(BaseModel):
    pass  # Mantén 'pass' si no quedan otros campos


class RespuestaEncuestaOut(RespuestaEncuestaBase):
    id: UUID
    entrega_id: UUID
    recibido_en: datetime
    respuestas_preguntas: List[RespuestaPreguntaOut] = []

    model_config = {"from_attributes": True}


class RespuestaCreateEmail(BaseModel):
    """Esquema para crear respuestas desde el enlace de email"""
    pregunta_id: str
    tipo_respuesta: str  # "texto", "numero", "opcion", "opciones"
    texto: Optional[str] = None
    numero: Optional[float] = None
    opcion_id: Optional[str] = None
    opciones_ids: Optional[List[str]] = None


class RespuestaDetalleItemOut(BaseModel):
    pregunta_id: Optional[UUID] = None
    pregunta: str
    tipo_pregunta_id: Optional[int] = None
    valor: Optional[str] = None
    respuesta: Optional[str] = None
    numero: Optional[float] = None
    opcion_id: Optional[UUID] = None
    metadatos: Optional[dict] = None

    model_config = {"from_attributes": True}


class DestinatarioRespuestaOut(BaseModel):
    id: Optional[UUID] = None
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None

    model_config = {"from_attributes": True}


class RespuestaListItemOut(BaseModel):
    id: UUID
    entrega_id: UUID
    campana_id: Optional[UUID] = None
    campana_nombre: Optional[str] = None
    creado_en: Optional[datetime] = None
    fecha: Optional[datetime] = None
    destinatario: Optional[DestinatarioRespuestaOut] = None
    detalles: List[RespuestaDetalleItemOut] = []
    respuestas: List[RespuestaDetalleItemOut] = []
    puntuacion: Optional[float] = None
    raw_payload: Optional[dict] = None

    model_config = {"from_attributes": True}
