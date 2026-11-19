# app/routers/contacto_router.py
from datetime import datetime, timezone
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit_ip
from app.core.security import get_admin_user
from app.models.contacto import Contacto
from app.schemas.auth import TokenData
from app.services.contacto_service import (
    ContactoOrigenEnum,
    ContactoTipoEnum,
    crear_contacto,
    despachar_correo_contacto,
    eliminar_datos_personales_procedimiento,
)
from app.services.email_service import _send_mail

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Contacto & Leads"])


class ContactoLeadCreate(BaseModel):
    nombre: str
    email: EmailStr
    empresa: Optional[str] = None
    mensaje: str
    origen: ContactoOrigenEnum = ContactoOrigenEnum.producto
    tipo: ContactoTipoEnum = ContactoTipoEnum.comercial

    @field_validator("origen", mode="before")
    @classmethod
    def validate_origen(cls, v):
        if v is None:
            return ContactoOrigenEnum.producto
        val = str(getattr(v, "value", v)).strip().lower()
        if val in ("producto", "corporativo"):
            return val
        raise ValueError(
            f"Origen no permitido: '{v}'. Valores permitidos: 'producto', 'corporativo'"
        )

    @field_validator("tipo", mode="before")
    @classmethod
    def validate_tipo(cls, v):
        if v is None:
            return ContactoTipoEnum.comercial
        val = str(getattr(v, "value", v)).strip().lower()
        if val in ("comercial", "soporte_tecnico", "derechos_datos"):
            return val
        if "soporte" in val:
            return "soporte_tecnico"
        if "derecho" in val or "arco" in val or "datos" in val:
            return "derechos_datos"
        raise ValueError(
            f"Tipo no permitido: '{v}'. Valores permitidos: 'comercial', 'soporte_tecnico', 'derechos_datos'"
        )


class ContactoLeadResponse(BaseModel):
    success: bool
    message: str
    contacto_id: Optional[UUID] = None


class ContactoOut(BaseModel):
    id: UUID
    nombre: str
    email: str
    empresa: Optional[str] = None
    mensaje: str
    origen: str
    tipo: str
    creado_en: datetime

    class Config:
        from_attributes = True


class EliminarDatosPersonaRequest(BaseModel):
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None
    motivo: str = "Solicitud de ejercicio de derechos sobre datos personales"


class SolicitarDemoCreate(BaseModel):
    email: EmailStr
    nombre: Optional[str] = None
    empresa: Optional[str] = None
    telefono: Optional[str] = None


class SolicitarDemoResponse(BaseModel):
    success: bool
    message: str


@router.post(
    "/contacto",
    response_model=ContactoLeadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ip(max_requests=5, window_seconds=60))],
)
@router.post(
    "/leads",
    response_model=ContactoLeadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ip(max_requests=5, window_seconds=60))],
)
@router.post(
    "/soporte",
    response_model=ContactoLeadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ip(max_requests=5, window_seconds=60))],
)
async def recibir_contacto_lead(
    payload: ContactoLeadCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Captura un prospecto/lead comercial, ticket de soporte o solicitud de derechos
    de datos desde formularios web, valida enums con 422, persiste en BD y despacha
    la alerta oficial por correo a Desesoft con origen y tipo.
    """
    forwarded = request.headers.get("x-forwarded-for")
    ip_origen = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)

    # Persistir en base de datos
    contacto = crear_contacto(
        db=db,
        nombre=payload.nombre,
        email=payload.email,
        mensaje=payload.mensaje,
        empresa=payload.empresa,
        origen=payload.origen,
        tipo=payload.tipo,
        ip_origen=ip_origen,
    )

    # Despachar correo a Desesoft
    try:
        await despachar_correo_contacto(contacto, sender=_send_mail)
    except Exception as exc:
        logger.error("Error despachando correo de contacto %s: %s", contacto.id, exc)

    return ContactoLeadResponse(
        success=True,
        message="Mensaje recibido correctamente. Nos pondremos en contacto contigo a la brevedad.",
        contacto_id=contacto.id,
    )


# ---------------- B2: Consultas y Derechos sobre los Datos (Admin) ----------------

@router.get(
    "/contacto/consultas",
    response_model=List[ContactoOut],
    dependencies=[Depends(get_admin_user)],
    summary="Listado de contactos para el administrador con filtro por tipo (B2)",
)
def listar_consultas_contacto(
    tipo: Optional[ContactoTipoEnum] = Query(None, description="Filtrar por tipo (ej: derechos_datos)"),
    origen: Optional[ContactoOrigenEnum] = Query(None, description="Filtrar por origen"),
    db: Session = Depends(get_db),
):
    query = db.query(Contacto)
    if tipo:
        query = query.filter(Contacto.tipo == tipo.value)
    if origen:
        query = query.filter(Contacto.origen == origen.value)
    return query.order_by(Contacto.creado_en.desc()).all()


@router.post(
    "/contacto/derechos-datos/eliminar",
    dependencies=[Depends(get_admin_user)],
    summary="Eliminación administrativa de respuestas y audios de una persona con bitácora de auditoría (B2)",
)
def eliminar_datos_persona_endpoint(
    payload: EliminarDatosPersonaRequest,
    admin: TokenData = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    admin_uuid = None
    try:
        admin_uuid = UUID(admin.sub)
    except Exception:
        pass

    try:
        resultado = eliminar_datos_personales_procedimiento(
            db=db,
            admin_id=admin_uuid,
            email=payload.email,
            telefono=payload.telefono,
            motivo=payload.motivo,
        )
        return {"success": True, **resultado}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))


# ---------------- Solicitud de Demos ----------------

@router.post("/solicitar-demo", response_model=SolicitarDemoResponse, status_code=status.HTTP_201_CREATED)
@router.post("/leads/demo", response_model=SolicitarDemoResponse, status_code=status.HTTP_201_CREATED)
async def solicitar_demo(payload: SolicitarDemoCreate):
    """
    Captura una solicitud de demo personalizada desde el banner principal de la Landing Page
    y despacha una alerta comercial prioritaria al correo administrativo,
    además de un correo de cortesía al usuario solicitante.
    """
    destinatario_admin = (
        getattr(settings, "ADMIN_NOTIFICATION_EMAIL", None) or
        settings.EMAIL_FROM or
        settings.SMTP_USERNAME or
        "dedasema734012@gmail.com"
    ).strip()

    fecha_solicitud = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    asunto_admin = f"🎯 Solicitud de Demo Personalizada: {payload.email}"

    html_admin = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <div style="background-color: #eff6ff; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #2563eb;">
            <span style="font-weight: bold; color: #1e40af; font-size: 14px;">🔥 PROSPECTO DE ALTA PRIORIDAD • DEMO SOLICITADA</span>
        </div>
        <h2 style="color: #1e293b; margin-top: 0;">Nueva Solicitud de Demo desde Landing Page</h2>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569; width: 140px;">Email:</td>
                <td style="padding: 10px; color: #1e293b;"><a href="mailto:{payload.email}" style="color: #2563eb; font-weight: bold;">{payload.email}</a></td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Nombre:</td>
                <td style="padding: 10px; color: #1e293b;">{payload.nombre or 'No especificado'}</td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Empresa:</td>
                <td style="padding: 10px; color: #1e293b;">{payload.empresa or 'No especificada'}</td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Teléfono:</td>
                <td style="padding: 10px; color: #1e293b;">{payload.telefono or 'No especificado'}</td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Fecha / Hora:</td>
                <td style="padding: 10px; color: #64748b;">{fecha_solicitud}</td>
            </tr>
        </table>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 25px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
            Notificación automática de SurveySaaS CRM • Registro instantáneo de demo comercial.<br>
            Impulsado por Desesoft — SurveySaaS
        </p>
    </div>
    """

    text_admin = f"""
    🎯 Solicitud de Demo Personalizada:
    - Email: {payload.email}
    - Nombre: {payload.nombre or 'No especificado'}
    - Empresa: {payload.empresa or 'No especificada'}
    - Teléfono: {payload.telefono or 'No especificado'}
    - Fecha: {fecha_solicitud}

    ---
    Impulsado por Desesoft — SurveySaaS
    """

    try:
        await _send_mail(
            destinatario_email=destinatario_admin,
            destinatario_nombre="Admin SurveySaaS",
            asunto=asunto_admin,
            html_content=html_admin,
            text_content=text_admin,
        )
    except Exception as e:
        logger.error("Error despachando correo de solicitud de demo a %s: %s", destinatario_admin, e)

    try:
        nombre_cliente = payload.nombre or "Colega"
        asunto_cliente = "¡Hemos recibido tu solicitud de Demo! - SurveySaaS"
        html_cliente = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
            <div style="text-align: center; margin-bottom: 20px;">
                <span style="font-size: 32px;">🎯</span>
                <h2 style="color: #1e293b; margin: 10px 0 5px;">¡Solicitud de Demo Recibida!</h2>
                <p style="color: #64748b; font-size: 14px; margin: 0;">SurveySaaS • Plataforma de Encuestas con IA y Multicanalidad</p>
            </div>
            <p style="color: #475569; font-size: 15px; line-height: 1.6;">
                Hola <strong>{nombre_cliente}</strong>,
            </p>
            <p style="color: #475569; font-size: 14px; line-height: 1.6;">
                Gracias por tu interés en <strong>SurveySaaS</strong>. Hemos recibido tu solicitud para coordinar una demostración personalizada del software.
            </p>
            <p style="color: #475569; font-size: 14px; line-height: 1.6;">
                Uno de nuestros asesores comerciales se pondrá en contacto contigo a la brevedad para agendar la sesión y mostrarte cómo potenciar tus encuestas corporativas con IA.
            </p>
            <div style="background-color: #f8fafc; padding: 15px; border-radius: 8px; margin: 20px 0; font-size: 13px; color: #64748b;">
                <strong>Detalle de tu solicitud:</strong><br>
                • Correo: {payload.email}<br>
                • Empresa: {payload.empresa or 'No especificada'}
            </div>
            <p style="color: #94a3b8; font-size: 12px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
                Desesoft S.R.L. • Santa Cruz de la Sierra, Bolivia.<br>
                Impulsado por Desesoft — SurveySaaS
            </p>
        </div>
        """
        text_cliente = f"""
        Hola {nombre_cliente},
        Gracias por tu interés en SurveySaaS. Hemos recibido tu solicitud de demo personalizada.
        Un asesor comercial se pondrá en contacto contigo muy pronto.

        ---
        Desesoft S.R.L. • Santa Cruz de la Sierra, Bolivia.
        Impulsado por Desesoft — SurveySaaS
        """
        await _send_mail(
            destinatario_email=payload.email,
            destinatario_nombre=nombre_cliente,
            asunto=asunto_cliente,
            html_content=html_cliente,
            text_content=text_cliente,
        )
    except Exception as e_c:
        logger.warning("No se pudo enviar correo de confirmación de demo a %s: %s", payload.email, e_c)

    return SolicitarDemoResponse(
        success=True,
        message="Solicitud de demo recibida exitosamente. Nos pondremos en contacto contigo a la brevedad.",
    )
