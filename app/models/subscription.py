import uuid
from sqlalchemy import Column, Integer, Text, Numeric, TIMESTAMP, ForeignKey, Boolean, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base

class PlanSuscripcion(Base):
    __tablename__ = "plan_suscripcion"
    
    id                  = Column(Integer, primary_key=True, index=True)
    nombre              = Column(Text, unique=True, nullable=False)
    precio_mensual      = Column(Numeric(10, 2), nullable=False)
    descripcion         = Column(Text, nullable=True)
    
    # Cuotas cuantitativas (-1 o 0 para ilimitado donde aplique)
    max_plantillas      = Column(Integer, nullable=False, default=5)
    max_campanas        = Column(Integer, nullable=False, default=5)
    max_entregas        = Column(Integer, nullable=False, default=500)
    max_operadores      = Column(Integer, nullable=False, default=1)
    
    # Permisos funcionales y por canal
    permite_email       = Column(Boolean, nullable=False, default=True)
    permite_audio_voz   = Column(Boolean, nullable=False, default=False)
    permite_papel       = Column(Boolean, nullable=False, default=False)
    permite_ia_analisis = Column(Boolean, nullable=False, default=False)
    permite_exportacion = Column(Boolean, nullable=False, default=True)
    
    # Características (separadas por ;) y estado
    caracteristicas     = Column(Text, nullable=True, default="")
    activo              = Column(Boolean, nullable=False, default=True)
    
    stripe_price_id     = Column(String(255), nullable=True)
    creado_en           = Column(TIMESTAMP(timezone=True), server_default=func.now())


class SuscripcionSuscriptor(Base):
    __tablename__ = "suscripcion_suscriptor"
    
    id                     = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suscriptor_id          = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=False)
    plan_id                = Column(Integer, ForeignKey("plan_suscripcion.id"), nullable=False)
    inicia_en              = Column(TIMESTAMP(timezone=True), nullable=False)
    expira_en              = Column(TIMESTAMP(timezone=True), nullable=True)
    estado                 = Column(Text, nullable=False, default="pendiente")
    stripe_subscription_id = Column(Text, nullable=True)

    suscriptor = relationship("Suscriptor")
    plan       = relationship("PlanSuscripcion")
