from pydantic import BaseModel, Field, EmailStr
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from app.schemas.subscription import PlanSuscripcionOut


class PlanResumenOut(BaseModel):
    id: int
    nombre: str
    precio_mensual: Decimal

    model_config = {"from_attributes": True}


class ResumenUsoAdminOut(BaseModel):
    plantillas_usadas: int = 0
    max_plantillas: int = 5
    campanas_activas: int = 0
    max_campanas: int = 5
    entregas_mes: int = 0
    max_entregas: int = 500
    limite_plan_entregas: Optional[int] = None
    bono_entregas: int = 0
    bono_paginas_ocr: int = 0
    bono_minutos_voz: int = 0
    operadores_activos: int = 0
    max_operadores: int = 1


class SuscriptorListOut(BaseModel):
    id: UUID
    nombre_empresa: str
    email_contacto: str
    telefono: Optional[str] = None
    estado: str
    creado_en: datetime
    plan: PlanResumenOut
    resumen_uso: ResumenUsoAdminOut

    model_config = {"from_attributes": True}


class SuscripcionActivaDetailOut(BaseModel):
    id: UUID
    inicia_en: datetime
    expira_en: Optional[datetime] = None
    estado: str

    model_config = {"from_attributes": True}


class SuscriptorDetail360Out(BaseModel):
    id: UUID
    nombre_empresa: str
    email_contacto: str
    telefono: Optional[str] = None
    estado: str
    creado_en: datetime
    stripe_customer_id: Optional[str] = None
    suscripcion_activa: Optional[SuscripcionActivaDetailOut] = None
    plan: PlanSuscripcionOut
    resumen_uso: ResumenUsoAdminOut

    model_config = {"from_attributes": True}


class SuscriptorEstadoUpdate(BaseModel):
    estado: str = Field(..., description="Estado de la empresa: activo | suspendido | pendiente")


class SuscriptorAsignarPlan(BaseModel):
    plan_id: int = Field(..., description="ID del plan a asignar a la empresa")


class CupoAdicionalUpdate(BaseModel):
    bono_entregas: Optional[int] = Field(None, ge=0, description="Cupo adicional de entregas/respuestas")
    bono_paginas_ocr: Optional[int] = Field(None, ge=0, description="Cupo adicional de páginas OCR")
    bono_minutos_voz: Optional[int] = Field(None, ge=0, description="Cupo adicional de minutos de voz")


class OperadorOut(BaseModel):
    id: UUID
    nombre_completo: str
    email: str
    activo: bool
    creado_en: Optional[datetime] = None

    model_config = {"from_attributes": True}
