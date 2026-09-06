# app/models/audio_respuesta.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, String, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class AudioRespuesta(Base):
    __tablename__ = "audio_respuesta"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entrega_id = Column(PGUUID(as_uuid=True), ForeignKey("entrega_encuesta.id", ondelete="CASCADE"), nullable=False, index=True)
    pregunta_id = Column(PGUUID(as_uuid=True), ForeignKey("pregunta_encuesta.id", ondelete="SET NULL"), nullable=True)
    archivo_url = Column(Text, nullable=False)
    formato = Column(String(10), nullable=False)
    duracion_segundos = Column(Float, nullable=True)
    estado_transcripcion = Column(String(20), default="pendiente", nullable=False, index=True)
    transcripcion_texto = Column(Text, nullable=True)
    error_detalle = Column(Text, nullable=True)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relaciones
    entrega = relationship("EntregaEncuesta")
    pregunta = relationship("PreguntaEncuesta")
