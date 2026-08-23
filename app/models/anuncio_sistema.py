import uuid
from sqlalchemy import Column, String, Text, Boolean, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from app.core.database import Base

class AnuncioSistema(Base):
    __tablename__ = "anuncio_sistema"

    id         = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo     = Column(String(255), nullable=False)
    mensaje    = Column(Text, nullable=False)
    tipo       = Column(String(50), default="info")  # info, warning, error, success
    activo     = Column(Boolean, default=True)
    creado_en  = Column(TIMESTAMP(timezone=True), server_default=func.now())
