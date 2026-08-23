from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from typing import Optional, List

class PlanSuscripcionBase(BaseModel):
    nombre: str
    precio_mensual: Decimal = Field(..., max_digits=10, decimal_places=2)
    descripcion: Optional[str] = None
    
    max_plantillas: int = Field(default=5, description="Número máximo de plantillas (-1 ilimitado)")
    max_campanas: int = Field(default=5, description="Número máximo de campañas (-1 ilimitado)")
    max_entregas: int = Field(default=500, description="Cuota mensual máxima de entregas (-1 ilimitado)")
    max_operadores: int = Field(default=1, description="Número máximo de cuentas de operador (-1 ilimitado)")
    
    permite_email: bool = Field(default=True)
    permite_audio_voz: bool = Field(default=False)
    permite_papel: bool = Field(default=False)
    permite_ia_analisis: bool = Field(default=False)
    permite_exportacion: bool = Field(default=True)
    
    caracteristicas: Optional[str] = ""
    activo: bool = Field(default=True)
    stripe_price_id: Optional[str] = None


class PlanSuscripcionCreate(PlanSuscripcionBase):
    pass


class PlanSuscripcionUpdate(BaseModel):
    nombre: Optional[str] = None
    precio_mensual: Optional[Decimal] = None
    descripcion: Optional[str] = None
    
    max_plantillas: Optional[int] = None
    max_campanas: Optional[int] = None
    max_entregas: Optional[int] = None
    max_operadores: Optional[int] = None
    
    permite_email: Optional[bool] = None
    permite_audio_voz: Optional[bool] = None
    permite_papel: Optional[bool] = None
    permite_ia_analisis: Optional[bool] = None
    permite_exportacion: Optional[bool] = None
    
    caracteristicas: Optional[str] = None
    activo: Optional[bool] = None
    stripe_price_id: Optional[str] = None


class PlanSuscripcionOut(PlanSuscripcionBase):
    id: int
    creado_en: datetime

    model_config = {"from_attributes": True}


class SuscripcionSuscriptorBase(BaseModel):
    suscriptor_id: UUID
    plan_id: int
    inicia_en: datetime
    expira_en: Optional[datetime] = None
    estado: Optional[str] = "activo"


class SuscripcionSuscriptorCreate(SuscripcionSuscriptorBase):
    pass


class SuscripcionSuscriptorUpdate(BaseModel):
    expira_en: Optional[datetime] = None
    estado: Optional[str] = None


class SuscripcionSuscriptorOut(SuscripcionSuscriptorBase):
    id: UUID
    plan: Optional[PlanSuscripcionOut] = None

    model_config = {"from_attributes": True}


class UsoActualOut(BaseModel):
    plantillas_usadas: int = 0
    campanas_activas: int = 0
    entregas_mes_actual: int = 0
    operadores_activos: int = 0


class MembresiaActualOut(BaseModel):
    id: str
    estado: str
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    dias_restantes: int = 0
    renovacion_automatica: bool = True
    plan: PlanSuscripcionOut
    uso_actual: UsoActualOut


class PagoSuscriptorOut(BaseModel):
    id: str
    referencia_stripe: Optional[str] = None
    monto: Decimal = Field(..., max_digits=10, decimal_places=2)
    moneda: str = "usd"
    fecha: datetime
    plan_nombre: str
    metodo_pago: str = "Tarjeta de Crédito / Débito"
    estado: str = "completado"
    recibo_url: Optional[str] = None

    model_config = {"from_attributes": True}


class PortalClienteOut(BaseModel):
    url: str


class PlanesList(BaseModel):
    planes: List[PlanSuscripcionOut]


class SuscripcionesList(BaseModel):
    suscripciones: List[SuscripcionSuscriptorOut]
