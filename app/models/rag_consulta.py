# app/models/rag_consulta.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base

class RagConsulta(Base):
    __tablename__ = "rag_consulta"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campana_id = Column(PGUUID(as_uuid=True), ForeignKey("campana_encuesta.id", ondelete="SET NULL"), nullable=True, index=True)
    pregunta = Column(Text, nullable=False)
    respuesta = Column(Text, nullable=False)
    fuentes_citadas = Column(JSONB, default=list)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relaciones
    campana = relationship("CampanaEncuesta")
