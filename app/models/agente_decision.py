# app/models/agente_decision.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, String, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base

class AgenteDecision(Base):
    __tablename__ = "agente_decision"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campana_id = Column(PGUUID(as_uuid=True), ForeignKey("campana_encuesta.id", ondelete="CASCADE"), nullable=False, index=True)
    campana_nombre = Column(String(255), nullable=True)
    trigger_evento = Column(Text, nullable=False)
    respuesta_id = Column(PGUUID(as_uuid=True), ForeignKey("respuesta_encuesta.id", ondelete="SET NULL"), nullable=True)
    tool_ejecutada = Column(String(100), nullable=False, index=True)
    parametros = Column(JSONB, default=dict)
    razonamiento_ia = Column(Text, nullable=False)
    estado = Column(String(20), default="ejecutado", nullable=False, index=True) # 'ejecutado', 'en_proceso', 'fallido', 'omitido'
    tiempo_ejecucion_ms = Column(Integer, default=0)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relaciones
    campana = relationship("CampanaEncuesta")
    respuesta = relationship("RespuestaEncuesta")
