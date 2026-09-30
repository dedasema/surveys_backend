# app/models/archivo_empresa.py
import uuid
from sqlalchemy import Column, String, Integer, Text, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class ArchivoEmpresa(Base):
    __tablename__ = "archivo_empresa"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(255), nullable=False)
    nombre_guardado = Column(String(255), nullable=False)
    ruta = Column(Text, nullable=False)
    extension = Column(String(20), nullable=False)
    peso_bytes = Column(Integer, nullable=False, default=0)
    mime_type = Column(String(100), nullable=False, default="application/octet-stream")
    categoria = Column(String(50), nullable=False, default="documento")
    contexto = Column(String(255), nullable=True)
    creado_por = Column(String(255), nullable=True)
    creado_en = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)

    suscriptor = relationship("Suscriptor")
