# app/models/agregado_campana.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class AgregadoCampana(Base):
    __tablename__ = "agregado_campana"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campana_id = Column(PGUUID(as_uuid=True), ForeignKey("campana_encuesta.id", ondelete="CASCADE"), nullable=False, index=True)
    periodo = Column(String(50), nullable=False) # 'Período 1', 'Sem 1', '2026-W36'
    total_respuestas = Column(Integer, default=0, nullable=False)
    promedio_satisfaccion = Column(Float, default=0.0, nullable=False)
    tasa_completitud = Column(Float, default=0.0, nullable=False)
    orden_periodo = Column(Integer, default=1, nullable=False)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relaciones
    campana = relationship("CampanaEncuesta")
