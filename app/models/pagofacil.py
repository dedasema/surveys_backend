# app/models/pagofacil.py
import uuid
from sqlalchemy import Column, String, Integer, Numeric, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class PagoFacilTransaccion(Base):
    __tablename__ = "pagofacil_transaccion"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_number = Column(String(100), unique=True, nullable=False, index=True)
    suscriptor_id = Column(PGUUID(as_uuid=True), ForeignKey("suscriptor.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("plan_suscripcion.id"), nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    moneda = Column(String(10), nullable=False, default="BOB")
    tipo_cambio = Column(Numeric(10, 2), nullable=False, default=6.96)
    estado = Column(String(50), nullable=False, default="pendiente", index=True)
    pagofacil_transaction_id = Column(String(100), nullable=True, index=True)
    qr_base64 = Column(Text, nullable=True)
    checkout_url = Column(Text, nullable=True)
    deep_link = Column(Text, nullable=True)
    qr_content_url = Column(Text, nullable=True)
    universal_url = Column(Text, nullable=True)
    fecha_expiracion = Column(TIMESTAMP(timezone=True), nullable=True)
    callback_payload = Column(JSONB, nullable=True)
    creado_en = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    actualizado_en = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    suscriptor = relationship("Suscriptor")
    plan = relationship("PlanSuscripcion")
