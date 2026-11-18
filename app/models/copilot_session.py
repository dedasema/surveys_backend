# app/models/copilot_session.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class CopilotSesion(Base):
    __tablename__ = "copilot_sesion"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    rol = Column(String(50), nullable=False, default="empresa")
    titulo = Column(String(255), nullable=False, default="Nueva conversación")
    campana_id = Column(PGUUID(as_uuid=True), ForeignKey("campana_encuesta.id", ondelete="SET NULL"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    actualizado_en = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relaciones
    suscriptor = relationship("Suscriptor")
    campana = relationship("CampanaEncuesta")
    mensajes = relationship("CopilotMensaje", back_populates="sesion", cascade="all, delete-orphan", order_by="CopilotMensaje.creado_en")

class CopilotMensaje(Base):
    __tablename__ = "copilot_mensaje"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sesion_id = Column(PGUUID(as_uuid=True), ForeignKey("copilot_sesion.id", ondelete="CASCADE"), nullable=False, index=True)
    sender = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    text = Column(Text, nullable=False)
    tools_used = Column(JSONB, default=list, nullable=True)
    fuentes_citadas = Column(JSONB, default=list, nullable=True)
    creado_en = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relaciones
    sesion = relationship("CopilotSesion", back_populates="mensajes")
