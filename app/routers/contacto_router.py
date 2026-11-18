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

@router.post("/contacto", response_model=ContactoLeadResponse, status_code=status.HTTP_201_CREATED)
@router.post("/leads", response_model=ContactoLeadResponse, status_code=status.HTTP_201_CREATED)
async def recibir_contacto_lead(payload: ContactoLeadCreate):
    """
    Captura un prospecto/lead comercial desde el formulario de la Landing Page
    y despacha una alerta por correo a la cuenta corporativa para seguimiento comercial.
    """
    destinatario_admin = settings.EMAIL_FROM or settings.SMTP_USERNAME or "dedasema734012@gmail.com"
    asunto = f"🚀 Nuevo Lead Comercial en SurveySaaS: {payload.nombre}"
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <h2 style="color: #1e293b; margin-top: 0;">Nuevo Lead Comercial desde la Landing Page</h2>
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
            <p style="font-weight: bold; color: #475569; margin-bottom: 5px;">Mensaje del interesado:</p>
            <div style="background-color: #f8fafc; padding: 15px; border-left: 4px solid #2563eb; border-radius: 4px; color: #334155; font-size: 14px; line-height: 1.6;">
                {payload.mensaje}
            </div>
        </div>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 25px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
            Notificación automática de SurveySaaS CRM • Contacto comercial recibido en tiempo real.
        </p>
    </div>
    """
    
    text_content = f"""
    Nuevo Lead Comercial desde Landing Page:
    - Nombre: {payload.nombre}
    - Email: {payload.email}
    - Empresa: {payload.empresa or 'No especificada'}
    - Mensaje: {payload.mensaje}
    """

    try:
        await _send_mail(
            destinatario_email=destinatario_admin,
            destinatario_nombre="Admin SurveySaaS",
            asunto=asunto,
            html_content=html_content,
            text_content=text_content
        )
    except Exception as e:
        logger.error(f"Error despachando correo de lead a {destinatario_admin}: {e}")

    return ContactoLeadResponse(
        success=True,
        message="Mensaje recibido correctamente. Nos pondremos en contacto contigo a la brevedad."
    )
