# app/models/audit_log.py
import uuid
from sqlalchemy import Column, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_log"

    id            = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    usuario_id    = Column(PGUUID(as_uuid=True), nullable=True)
    usuario_email = Column(String(255), nullable=True)
    rol           = Column(String(50), nullable=True)
    accion        = Column(String(50), nullable=False)   # CREAR, MODIFICAR, ELIMINAR, ASIGNAR_PERMISOS, LOGIN, EXPORTAR
    modulo        = Column(String(50), nullable=False)   # ROLES, PLANTILLAS, CAMPANAS, DESTINATARIOS, ENTREGAS, AUTH
    entidad_id    = Column(String(100), nullable=True)
    detalles      = Column(JSONB, nullable=True)
    ip_address    = Column(String(50), nullable=True)
    creado_en     = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
