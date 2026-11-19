# app/models/contacto.py
import uuid
from sqlalchemy import Column, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from app.core.database import Base


class Contacto(Base):
    __tablename__ = "contacto"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    empresa = Column(String(255), nullable=True)
    mensaje = Column(Text, nullable=False)
    origen = Column(String(50), nullable=False, default="producto")
    tipo = Column(String(50), nullable=False, default="comercial", index=True)
    ip_origen = Column(String(50), nullable=True)
    creado_en = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
