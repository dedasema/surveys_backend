from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional

class AnuncioSistemaBase(BaseModel):
    titulo: str = Field(..., max_length=255, description="Título del anuncio global")
    mensaje: str = Field(..., description="Contenido o mensaje del aviso")
    tipo: str = Field("info", description="Tipo de alerta: info | warning | error | success")
    activo: bool = True

class AnuncioSistemaCreate(AnuncioSistemaBase):
    pass

class AnuncioSistemaUpdate(BaseModel):
    titulo: Optional[str] = None
    mensaje: Optional[str] = None
    tipo: Optional[str] = None
    activo: Optional[bool] = None

class AnuncioSistemaOut(AnuncioSistemaBase):
    id: UUID
    creado_en: datetime

    model_config = {"from_attributes": True}
