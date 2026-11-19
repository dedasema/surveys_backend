# app/services/contacto_service.py
import logging
from enum import Enum
from typing import Optional, List, Tuple, Any
from uuid import UUID
from datetime import datetime, timezone
import os

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models.contacto import Contacto
from app.models.survey import Destinatario, EntregaEncuesta, RespuestaEncuesta, RespuestaPregunta
from app.models.audio_respuesta import AudioRespuesta
from app.models.audit_log import AuditLog
from app.core.config import settings
from app.services.email_service import _send_mail

logger = logging.getLogger(__name__)


class ContactoOrigenEnum(str, Enum):
    producto = "producto"
    corporativo = "corporativo"


class ContactoTipoEnum(str, Enum):
    comercial = "comercial"
    soporte_tecnico = "soporte_tecnico"
    derechos_datos = "derechos_datos"


def normalizar_origen(origen) -> str:
    if hasattr(origen, "value"):
        origen = origen.value
    origen_str = str(origen or "producto").strip().lower()
    if "corp" in origen_str or "desesoft" in origen_str:
        return "corporativo"
    return "producto"


def normalizar_tipo(tipo) -> str:
    if hasattr(tipo, "value"):
        tipo = tipo.value
    tipo_str = str(tipo or "comercial").strip().lower()
    if "derecho" in tipo_str or "datos" in tipo_str or "arco" in tipo_str:
        return "derechos_datos"
    if "soporte" in tipo_str or "tecnic" in tipo_str or "técnic" in tipo_str or "ticket" in tipo_str:
        return "soporte_tecnico"
    return "comercial"


def formatear_tipo_label(tipo) -> str:
    val = tipo.value if hasattr(tipo, "value") else str(tipo)
    val = val.lower()
    if "derecho" in val or "datos" in val:
        return "Derechos sobre datos"
    elif "soporte" in val or "tecnic" in val:
        return "Soporte Técnico"
    return "Comercial"


def crear_contacto(
    db: Session,
    nombre: str,
    email: str,
    mensaje: str,
    empresa: Optional[str] = None,
    origen: Any = ContactoOrigenEnum.producto,
    tipo: Any = ContactoTipoEnum.comercial,
    ip_origen: Optional[str] = None,
) -> Contacto:
    origen_norm = normalizar_origen(origen)
    tipo_norm = normalizar_tipo(tipo)

    contacto = Contacto(
        nombre=nombre.strip(),
        email=email.strip().lower(),
        empresa=empresa.strip() if empresa else None,
        mensaje=mensaje.strip(),
        origen=origen_norm,
        tipo=tipo_norm,
        ip_origen=ip_origen,
    )
    db.add(contacto)
    db.commit()
    db.refresh(contacto)
    logger.info("Contacto guardado en BD: id=%s origen=%s tipo=%s", contacto.id, contacto.origen, contacto.tipo)
    return contacto


async def despachar_correo_contacto(contacto: Contacto, sender=None) -> bool:
    send_fn = sender or _send_mail
    destinatario_admin = (
        getattr(settings, "ADMIN_NOTIFICATION_EMAIL", None) or
        settings.EMAIL_FROM or
        settings.SMTP_USERNAME or
        "dedasema734012@gmail.com"
    ).strip()

    tipo_label = formatear_tipo_label(contacto.tipo)
    origen_val = contacto.origen

    # Asunto con formato estricto: [Tipo · origen] ...
    if contacto.tipo == ContactoTipoEnum.derechos_datos.value:
        asunto = f"[{tipo_label} · {origen_val}] Solicitud de ejercicio de derechos: {contacto.nombre}"
        titulo_box = "Solicitud Prioritaria: Derechos sobre los Datos Personales"
        pie_box = "ALERTA LEGAL: El usuario solicita el ejercicio de derechos sobre sus datos personales."
    elif contacto.tipo == ContactoTipoEnum.soporte_tecnico.value:
        asunto = f"[{tipo_label} · {origen_val}] Ticket de Soporte Técnico: {contacto.nombre}"
        titulo_box = "Nueva Solicitud de Soporte Técnico"
        pie_box = "Notificación automática de SurveySaaS • Centro de Soporte al Cliente."
    else:
        asunto = f"[{tipo_label} · {origen_val}] Nuevo Lead Comercial: {contacto.nombre}"
        titulo_box = "Nuevo Lead Comercial"
        pie_box = "Notificación automática de SurveySaaS CRM • Contacto comercial recibido en tiempo real."

    badge_bg = "#dc2626" if contacto.tipo == ContactoTipoEnum.derechos_datos.value else "#2563eb"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <div style="display: inline-block; background-color: {badge_bg}; color: #ffffff; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-bottom: 12px;">
            {tipo_label.upper()} · {origen_val.upper()}
        </div>
        <h2 style="color: #1e293b; margin-top: 0;">{titulo_box}</h2>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569; width: 140px;">Origen:</td>
                <td style="padding: 10px; color: #1e293b;"><strong>{origen_val}</strong></td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Tipo:</td>
                <td style="padding: 10px; color: #1e293b;"><strong>{tipo_label}</strong></td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Nombre:</td>
                <td style="padding: 10px; color: #1e293b;">{contacto.nombre}</td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Email:</td>
                <td style="padding: 10px; color: #1e293b;"><a href="mailto:{contacto.email}" style="color: #2563eb;">{contacto.email}</a></td>
            </tr>
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; font-weight: bold; color: #475569;">Empresa:</td>
                <td style="padding: 10px; color: #1e293b;">{contacto.empresa or 'No especificada'}</td>
            </tr>
        </table>
        <div style="margin-top: 15px;">
            <p style="font-weight: bold; color: #475569; margin-bottom: 5px;">Mensaje:</p>
            <div style="background-color: #f8fafc; padding: 15px; border-left: 4px solid {badge_bg}; border-radius: 4px; color: #334155; font-size: 14px; line-height: 1.6;">
                {contacto.mensaje}
            </div>
        </div>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 25px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
            {pie_box}<br>
            Impulsado por Desesoft — SurveySaaS
        </p>
    </div>
    """

    text_content = f"""
    [{tipo_label} · {origen_val}] {titulo_box}:
    - Origen: {origen_val}
    - Tipo: {tipo_label}
    - Nombre: {contacto.nombre}
    - Email: {contacto.email}
    - Empresa: {contacto.empresa or 'No especificada'}
    - Mensaje: {contacto.mensaje}

    ---
    Impulsado por Desesoft — SurveySaaS
    """

    return await send_fn(destinatario_admin, "Administrador Desesoft", asunto, html_content, text_content)


def eliminar_datos_personales_procedimiento(
    db: Session,
    admin_id: Optional[UUID],
    email: Optional[str] = None,
    telefono: Optional[str] = None,
    motivo: str = "Solicitud de ejercicio de derechos sobre datos personales",
) -> dict:
    """
    Procedimiento administrativo para eliminar las respuestas y los audios de una persona
    a solicitud, con registro estricto en la bitácora de auditoría.
    """
    if not email and not telefono:
        raise ValueError("Debe proporcionar al menos un correo o un teléfono para identificar a la persona.")

    criterios = []
    if email:
        criterios.append(func.lower(Destinatario.email) == email.strip().lower())
    if telefono:
        criterios.append(Destinatario.telefono == telefono.strip())

    destinatarios = db.query(Destinatario).filter(or_(*criterios)).all()
    if not destinatarios:
        return {
            "destinatarios_encontrados": 0,
            "entregas_afectadas": 0,
            "respuestas_eliminadas": 0,
            "audios_eliminados": 0,
            "mensaje": "No se encontraron registros asociados al correo o teléfono proporcionado.",
        }

    total_respuestas = 0
    total_audios = 0
    entregas_afectadas_ids = []

    for dest in destinatarios:
        entregas = db.query(EntregaEncuesta).filter(EntregaEncuesta.destinatario_id == dest.id).all()
        for ent in entregas:
            entregas_afectadas_ids.append(ent.id)

            # 1. Eliminar audios físicos y registros de audio
            audios = db.query(AudioRespuesta).filter(AudioRespuesta.entrega_id == ent.id).all()
            for aud in audios:
                total_audios += 1
                if aud.archivo_url and aud.archivo_url.startswith("/uploads/"):
                    ruta_disco = aud.archivo_url.lstrip("/")
                    if os.path.exists(ruta_disco):
                        try:
                            os.remove(ruta_disco)
                        except Exception as exc:
                            logger.warning("No se pudo borrar archivo de audio local %s: %s", ruta_disco, exc)
                db.delete(aud)

            # 2. Eliminar respuestas a preguntas y respuestas de encuesta
            respuestas = db.query(RespuestaEncuesta).filter(RespuestaEncuesta.entrega_id == ent.id).all()
            for r in respuestas:
                total_respuestas += 1
                db.query(RespuestaPregunta).filter(RespuestaPregunta.respuesta_id == r.id).delete()
                db.delete(r)

            # 3. Anonimizar o limpiar estado de la entrega
            ent.destinatario_id = None
            ent.respondido_en = None

        # 4. Eliminar el registro del destinatario
        db.delete(dest)

    # 5. Registro obligatorio en la bitácora de auditoría (AuditLog)
    identificador = email or telefono or "desconocido"
    audit = AuditLog(
        suscriptor_id=None,
        usuario_id=admin_id,
        accion="DERECHOS_DATOS_ELIMINACION",
        entidad="Destinatario/RespuestaEncuesta/AudioRespuesta",
        entidad_id=identificador,
        detalles=(
            f"Se ejecutó el derecho de supresión de datos personales para '{identificador}'. "
            f"Respuestas eliminadas: {total_respuestas}, Audios eliminados: {total_audios}. Motivo: {motivo}"
        ),
    )
    db.add(audit)
    db.commit()

    logger.info(
        "Procedimiento de derechos de datos completado para %s: %d respuestas, %d audios eliminados.",
        identificador,
        total_respuestas,
        total_audios,
    )

    return {
        "destinatarios_encontrados": len(destinatarios),
        "entregas_afectadas": len(entregas_afectadas_ids),
        "respuestas_eliminadas": total_respuestas,
        "audios_eliminados": total_audios,
        "mensaje": f"Se eliminaron exitosamente {total_respuestas} respuestas y {total_audios} audios de la persona.",
    }
