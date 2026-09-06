# app/models/regla_ramificacion.py
import uuid
from sqlalchemy import Column, Text, Boolean, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class ReglaRamificacion(Base):
    __tablename__ = "regla_ramificacion"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plantilla_id = Column(PGUUID(as_uuid=True), ForeignKey("plantilla_encuesta.id", ondelete="CASCADE"), nullable=False, index=True)
    pregunta_origen_id = Column(PGUUID(as_uuid=True), ForeignKey("pregunta_encuesta.id", ondelete="CASCADE"), nullable=False, index=True)
    condicion_semantica = Column(Text, nullable=False)
    pregunta_destino_id = Column(PGUUID(as_uuid=True), ForeignKey("pregunta_encuesta.id", ondelete="SET NULL"), nullable=True)
    es_fin_encuesta = Column(Boolean, default=False, nullable=False)
    orden_prioridad = Column(Integer, default=1, nullable=False)

    # Relaciones
    plantilla = relationship("PlantillaEncuesta")
    pregunta_origen = relationship("PreguntaEncuesta", foreign_keys=[pregunta_origen_id])
    pregunta_destino = relationship("PreguntaEncuesta", foreign_keys=[pregunta_destino_id])
