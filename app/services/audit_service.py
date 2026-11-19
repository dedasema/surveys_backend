# app/services/audit_service.py
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import Request

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

def registrar_auditoria(
    db: Session,
    accion: str,
    modulo: str,
    usuario_id: Optional[UUID] = None,
    usuario_email: Optional[str] = None,
    rol: Optional[str] = None,
    suscriptor_id: Optional[UUID] = None,
    entidad_id: Optional[str] = None,
    detalles: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Registra un evento administrativo o relevante en la tabla de auditoría.
    """
    try:
        log_entry = AuditLog(
            suscriptor_id=suscriptor_id,
            usuario_id=usuario_id,
            usuario_email=usuario_email,
            rol=rol,
            accion=accion.upper(),
            modulo=modulo.upper(),
            entidad_id=str(entidad_id) if entidad_id else None,
            detalles=detalles or {},
            ip_address=ip_address,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as e:
        db.rollback()
        logger.error("Error registrando auditoria: %s", e)
        return None

def listar_auditoria(
    db: Session,
    modulo: Optional[str] = None,
    accion: Optional[str] = None,
    usuario_id: Optional[UUID] = None,
    suscriptor_id: Optional[UUID] = None,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[AuditLog]:
    query = db.query(AuditLog)

    if modulo:
        query = query.filter(AuditLog.modulo == modulo.upper())
    if accion:
        query = query.filter(AuditLog.accion == accion.upper())
    if usuario_id:
        query = query.filter(AuditLog.usuario_id == usuario_id)
    if suscriptor_id:
        query = query.filter(AuditLog.suscriptor_id == suscriptor_id)
    if fecha_inicio:
        query = query.filter(AuditLog.creado_en >= fecha_inicio)
    if fecha_fin:
        query = query.filter(AuditLog.creado_en <= fecha_fin)

    return query.order_by(AuditLog.creado_en.desc()).offset(offset).limit(limit).all()

def contar_auditoria(
    db: Session,
    modulo: Optional[str] = None,
    accion: Optional[str] = None,
    suscriptor_id: Optional[UUID] = None,
) -> int:
    query = db.query(AuditLog)
    if modulo:
        query = query.filter(AuditLog.modulo == modulo.upper())
    if accion:
        query = query.filter(AuditLog.accion == accion.upper())
    if suscriptor_id:
        query = query.filter(AuditLog.suscriptor_id == suscriptor_id)
    return query.count()
