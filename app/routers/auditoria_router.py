# app/routers/auditoria_router.py
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.auth import TokenData
from app.services.audit_service import listar_auditoria, contar_auditoria

router = APIRouter(prefix="/auditoria", tags=["Auditoría"])

class AuditLogOut(BaseModel):
    id: UUID
    usuario_id: Optional[UUID] = None
    usuario_email: Optional[str] = None
    rol: Optional[str] = None
    accion: str
    modulo: str
    entidad_id: Optional[str] = None
    detalles: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    creado_en: datetime

    class Config:
        from_attributes = True

class AuditListResponse(BaseModel):
    total: int
    items: List[AuditLogOut]

@router.get("", response_model=AuditListResponse)
async def get_audit_logs(
    modulo: Optional[str] = None,
    accion: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retorna los registros de auditoría global del sistema.
    Solo accesible por administradores y usuarios con permisos de auditoría.
    """
    if token_data.role not in ["admin", "empresa"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para consultar el registro de auditoría"
        )

    total = contar_auditoria(db, modulo=modulo, accion=accion)
    items = listar_auditoria(db, modulo=modulo, accion=accion, limit=limit, offset=offset)

    return AuditListResponse(total=total, items=items)

@router.get("/filtros")
async def get_audit_filters(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retorna listas de módulos y acciones presentes para poblar selectores en frontend.
    """
    if token_data.role not in ["admin", "empresa"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para consultar filtros de auditoría"
        )

    from app.models.audit_log import AuditLog
    modulos = [r[0] for r in db.query(AuditLog.modulo).distinct().all() if r[0]]
    acciones = [r[0] for r in db.query(AuditLog.accion).distinct().all() if r[0]]

    # Si aún no hay registros, retornar listas predeterminadas
    default_modulos = ["ROLES", "PLANTILLAS", "CAMPANAS", "DESTINATARIOS", "ENTREGAS", "AUTH", "SUSCRIPTORES"]
    default_acciones = ["CREAR", "MODIFICAR", "ELIMINAR", "ASIGNAR_PERMISOS", "LOGIN", "EXPORTAR"]

    return {
        "modulos": sorted(list(set(modulos + default_modulos))),
        "acciones": sorted(list(set(acciones + default_acciones))),
    }
