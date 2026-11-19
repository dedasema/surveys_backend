# app/routers/contacto_router.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging
from app.services.email_service import _send_mail
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Contacto & Leads"])

class ContactoLeadCreate(BaseModel):
    nombre: str
    email: EmailStr
    empresa: Optional[str] = None
    mensaje: str

class ContactoLeadResponse(BaseModel):
    success: bool
    message: str

class SolicitarDemoCreate(BaseModel):
    email: EmailStr
    nombre: Optional[str] = None
    empresa: Optional[str] = None
    telefono: Optional[str] = None

class SolicitarDemoResponse(BaseModel):
    success: bool
    message: str

@router.post("/contacto", response_model=ContactoLeadResponse, status_code=status.HTTP_201_CREATED)
@router.post("/leads", response_model=ContactoLeadResponse, status_code=status.HTTP_201_CREATED)
@router.post("/soporte", response_model=ContactoLeadResponse, status_code=status.HTTP_201_CREATED)
async def recibir_contacto_lead(payload: ContactoLeadCreate):
    """
    Captura un prospecto/lead comercial o ticket de soporte desde los formularios web
    y despacha una alerta por correo a la cuenta corporativa/administrador.
    """
    destinatario_admin = (
        getattr(settings, "ADMIN_NOTIFICATION_EMAIL", None) or
        settings.EMAIL_FROM or
        settings.SMTP_USERNAME or
        "dedasema734012@gmail.com"
    ).strip()

    es_soporte = (
        payload.mensaje.strip().startswith("[") or
        "soporte" in payload.mensaje.lower() or
        "ticket" in payload.mensaje.lower() or
        "ayuda" in payload.mensaje.lower()
    )

    if es_soporte:
        asunto = f"🛠️ Nuevo Ticket de Soporte SurveySaaS: {payload.nombre}"
        titulo_box = "Nueva Solicitud de Soporte Técnico"
        pie_box = "Notificación automática de SurveySaaS • Centro de Soporte al Cliente."
    else:
        asunto = f"🚀 Nuevo Lead Comercial en SurveySaaS: {payload.nombre}"
        titulo_box = "Nuevo Lead Comercial desde la Landing Page"
        pie_box = "Notificación automática de SurveySaaS CRM • Contacto comercial recibido en tiempo real."
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <h2 style="color: #1e293b; margin-top: 0;">{titulo_box}</h2>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569; width: 140px;">Nombre:</td>
                <td style="padding: 10px; color: #1e293b;">{payload.nombre}</td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Email:</td>
                <td style="padding: 10px; color: #1e293b;"><a href="mailto:{payload.email}" style="color: #2563eb;">{payload.email}</a></td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Empresa:</td>
                <td style="padding: 10px; color: #1e293b;">{payload.empresa or 'No especificada'}</td>
            </tr>
        </table>
        <div style="margin-top: 15px;">
            <p style="font-weight: bold; color: #475569; margin-bottom: 5px;">Mensaje:</p>
            <div style="background-color: #f8fafc; padding: 15px; border-left: 4px solid #2563eb; border-radius: 4px; color: #334155; font-size: 14px; line-height: 1.6;">
                {payload.mensaje}
            </div>
        </div>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 25px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
            {pie_box}
        </p>
    </div>
    """
    
    text_content = f"""
    {titulo_box}:
    - Nombre: {payload.nombre}
    - Email: {payload.email}
    - Empresa: {payload.empresa or 'No especificada'}
    - Mensaje: {payload.mensaje}
    """

    try:
        enviado = await _send_mail(
            destinatario_email=destinatario_admin,
            destinatario_nombre="Admin SurveySaaS",
            asunto=asunto,
            html_content=html_content,
            text_content=text_content
        )
        if not enviado:
            logger.warning(f"No se pudo despachar el correo de contacto a {destinatario_admin}")
    except Exception as e:
        logger.error(f"Error despachando correo de lead a {destinatario_admin}: {e}")

    return ContactoLeadResponse(
        success=True,
        message="Mensaje recibido correctamente. Nos pondremos en contacto contigo a la brevedad."
    )


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

    from datetime import datetime, timezone
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
            Notificación automática de SurveySaaS CRM • Registro instantáneo de demo comercial.
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
    """

    # 1. Enviar notificación al equipo comercial/admin
    try:
        await _send_mail(
            destinatario_email=destinatario_admin,
            destinatario_nombre="Admin SurveySaaS",
            asunto=asunto_admin,
            html_content=html_admin,
            text_content=text_admin
        )
    except Exception as e:
        logger.error(f"Error despachando correo de solicitud de demo a {destinatario_admin}: {e}")

    # 2. Correo de cortesía automático al interesado
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
                Deseosoft SRL • Santa Cruz de la Sierra, Bolivia.
            </p>
        </div>
        """
        text_cliente = f"""
        Hola {nombre_cliente},
        Gracias por tu interés en SurveySaaS. Hemos recibido tu solicitud de demo personalizada.
        Un asesor comercial se pondrá en contacto contigo muy pronto.
        """
        await _send_mail(
            destinatario_email=payload.email,
            destinatario_nombre=nombre_cliente,
            asunto=asunto_cliente,
            html_content=html_cliente,
            text_content=text_cliente
        )
    except Exception as e_c:
        logger.warning(f"No se pudo enviar correo de confirmación de demo a {payload.email}: {e_c}")

    return SolicitarDemoResponse(
        success=True,
        message="Solicitud de demo recibida exitosamente. Nos pondremos en contacto contigo a la brevedad."
    )
