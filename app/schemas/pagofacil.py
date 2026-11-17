# app/schemas/pagofacil.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any

class GenerarQRPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    monto: Optional[float] = None
    moneda: Optional[str] = "BOB"
    document_type: Optional[int] = 1
    document_id: Optional[str] = None
    client_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    callback_url: Optional[str] = None

class GenerarQRResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    success: bool
    payment_number: str
    transaction_id: Optional[str] = None
    status: str
    qr_base64: Optional[str] = None
    checkout_url: Optional[str] = None
    deep_link: Optional[str] = None
    qr_content_url: Optional[str] = None
    universal_url: Optional[str] = None
    expiration_date: Optional[str] = None
    monto: float
    moneda: str
    plan_nombre: str

class ConsultarTransaccionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    success: bool
    payment_number: str
    estado: str
    pagado: bool
    monto: float
    moneda: str
    pagofacil_transaction_id: Optional[str] = None
    fecha_pago: Optional[str] = None
    mensaje: str

class PagoFacilCallbackPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    PedidoID: str
    Fecha: Optional[str] = None
    Hora: Optional[str] = None
    MetodoPago: Optional[str] = None
    Estado: Optional[Any] = None

class PagoFacilCallbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error: int = 0
    status: int = 1
    message: str = "Pago procesado exitosamente"
    values: bool = True

class MetodoHabilitadoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paymentMethodId: int
    paymentMethodName: str
    currencyName: str
    maxAmountPerDay: Optional[float] = None
    maxAmountPerTransaction: Optional[float] = None

class MetodosHabilitadosResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error: int = 0
    status: int = 2006
    message: str
    values: List[MetodoHabilitadoItem]

class PagoFacilTransaccionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    payment_number: str
    plan_id: int
    monto: float
    moneda: str
    estado: str
    pagofacil_transaction_id: Optional[str] = None
    qr_base64: Optional[str] = None
    checkout_url: Optional[str] = None
    creado_en: Optional[str] = None
