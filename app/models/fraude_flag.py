# app/models/fraude_flag.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, String, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class FraudeFlag(Base):
    __tablename__ = "fraude_flag"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    respuesta_id = Column(PGUUID(as_uuid=True), ForeignKey("respuesta_encuesta.id", ondelete="CASCADE"), nullable=False, index=True)
    campana_id = Column(PGUUID(as_uuid=True), ForeignKey("campana_encuesta.id", ondelete="CASCADE"), nullable=False, index=True)
    canal = Column(String(20), default="web", nullable=False) # 'gmail', 'ocr', 'voz', 'web'
    tipo_senal = Column(String(20), nullable=False) # 'regla', 'similitud', 'score_ia'
    confianza = Column(Float, nullable=False) # 0.0 a 1.0
    contenido_respuesta = Column(Text, nullable=False)
    respuesta_similar = Column(Text, nullable=True)
    similitud_score = Column(Float, nullable=True)
    justificacion = Column(Text, nullable=True)
    estado = Column(String(30), default="pendiente", nullable=False, index=True) # 'pendiente', 'confirmado_fraude', 'descartado_valido'
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relaciones
    respuesta = relationship("RespuestaEncuesta")
    campana = relationship("CampanaEncuesta")
