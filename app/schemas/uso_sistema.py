# app/schemas/uso_sistema.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any

class ActividadDia(BaseModel):
    fecha: str
    cantidad: int

class TopUsuarioActividad(BaseModel):
    usuario_id: Optional[str] = None
    email: str
    nombre: str
    rol: Optional[str] = None
    total_operaciones: int

class OperacionesCUDDetalle(BaseModel):
    crear: int
    modificar: int
    eliminar: int
    otros: int
    total: int
    porcentajes: Dict[str, float]

class EspacioUsadoMetricas(BaseModel):
    bytes: int
    mb: float
    limite_mb: float
    porcentaje_usado: float
    unidad: str
    formateado: str

class UsoSistemaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ultima_sesion: Optional[str] = None
    espacio_usado: EspacioUsadoMetricas
    pago_total_acumulado: float
    moneda: str
    frecuencia_pago: str
    plan_nombre: str
    estado_suscripcion: str
    proximo_pago: Optional[str] = None
    grafica_dias_mayor_uso: List[ActividadDia]
    dia_pico: Optional[ActividadDia] = None
    top_5_usuarios: List[TopUsuarioActividad]
    tipos_operaciones_cud: OperacionesCUDDetalle
