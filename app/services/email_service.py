try:
    import aiosmtplib
except Exception:
    aiosmtplib = None

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import logging
import asyncio
import smtplib
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

def _parse_sender(raw_sender: str, default_email: str):
    if not raw_sender:
        raw_sender = default_email
    if "<" in raw_sender and ">" in raw_sender:
        name = raw_sender.split("<")[0].strip()
        email = raw_sender.split("<")[1].split(">")[0].strip()
        return name or "SurveySaaS", email
    return "SurveySaaS", raw_sender.strip()

async def _send_mail(
    destinatario_email: str,
    destinatario_nombre: str,
    asunto: str,
    html_content: str,
    text_content: str
) -> bool:
    """
    Envía un correo utilizando Google Apps Script Webhook (Gmail por HTTPS 443),
    Brevo HTTP API, Resend HTTP API, o SMTP como alternativa.
    """
    # 0. Intentar vía Google Apps Script Webhook (Gmail directo sobre HTTPS puerto 443)
    if settings.GMAIL_WEBHOOK_URL and settings.GMAIL_WEBHOOK_URL.strip():
        try:
            s_name, _ = _parse_sender(settings.EMAIL_FROM or "", "SurveySaaS")
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                res = await client.post(
                    settings.GMAIL_WEBHOOK_URL.strip(),
                    json={
                        "to": destinatario_email,
                        "subject": asunto,
                        "html": html_content,
                        "text": text_content,
                        "sender_name": s_name,
                        "secret": settings.GMAIL_SECRET_TOKEN or ""
                    }
                )
                if res.status_code in (200, 201):
                    logger.info(f"Correo enviado exitosamente a {destinatario_email} vía Google Apps Script Webhook")
                    return True
                else:
                    logger.error(f"Google Apps Script Webhook devolvió error {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Excepción llamando a Google Apps Script Webhook: {e}")

    # 1. Intentar vía Brevo HTTP API (Recomendado para Render Free - No requiere dominio propio)
    if settings.BREVO_API_KEY and settings.BREVO_API_KEY.strip():
        try:
            s_name, s_email = _parse_sender(
                settings.EMAIL_FROM or settings.SMTP_USERNAME or "",
                settings.SMTP_USERNAME or "noreply@surveysaas.com"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": settings.BREVO_API_KEY.strip(),
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    json={
                        "sender": {"name": s_name, "email": s_email},
                        "to": [{"email": destinatario_email, "name": destinatario_nombre}],
                        "subject": asunto,
                        "htmlContent": html_content,
                        "textContent": text_content
                    }
                )
                if res.status_code in (200, 201):
                    logger.info(f"Correo enviado exitosamente a {destinatario_email} vía Brevo HTTP API")
                    return True
                else:
                    logger.error(f"Brevo API devolvió error {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Excepción llamando a Brevo HTTP API: {e}")

    # 2. Intentar vía Resend HTTP API
    if settings.RESEND_API_KEY and settings.RESEND_API_KEY.strip():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.RESEND_API_KEY.strip()}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": settings.EMAIL_FROM or "SurveySaaS <onboarding@resend.dev>",
                        "to": [destinatario_email],
                        "subject": asunto,
                        "html": html_content,
                        "text": text_content
                    }
                )
                if res.status_code in (200, 201):
                    logger.info(f"Correo enviado exitosamente a {destinatario_email} vía Resend HTTP API")
                    return True
                else:
                    logger.error(f"Resend API devolvió error {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Excepción llamando a Resend HTTP API: {e}")

    # 3. Intentar vía SMTP (puerto 587/465)
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        logger.warning(f"No se pudo enviar correo a {destinatario_email}: Sin credenciales de Brevo/Resend ni SMTP")
        return False

    try:
        clean_password = settings.SMTP_PASSWORD.replace(" ", "").strip()
        message = MIMEMultipart("alternative")
        message["Subject"] = Header(asunto, "utf-8")
        message["From"] = f"{settings.SMTP_USERNAME}"
        message["To"] = f"{destinatario_nombre} <{destinatario_email}>"
        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))

        if aiosmtplib is not None:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_SERVER,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME,
                password=clean_password,
                start_tls=(settings.SMTP_PORT == 587),
                use_tls=(settings.SMTP_PORT == 465),
                timeout=10.0
            )
        else:
            def _sync_send():
                if settings.SMTP_PORT == 465:
                    with smtplib.SMTP_SSL(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=10.0) as server:
                        server.login(settings.SMTP_USERNAME, clean_password)
                        server.send_message(message)
                else:
                    with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=10.0) as server:
                        server.starttls()
                        server.login(settings.SMTP_USERNAME, clean_password)
                        server.send_message(message)

            await asyncio.to_thread(_sync_send)

        logger.info(f"Email enviado a {destinatario_email} vía SMTP")
        return True

    except Exception as e:
        logger.error(f"Error enviando email vía SMTP: {str(e)}")
        return False


async def enviar_email(
    destinatario_email: str,
    destinatario_nombre: str,
    asunto: str,
    nombre_campana: str,
    nombre_empresa: str, 
    url_encuesta: str
) -> bool:
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 5px;">
        <h2 style="color: #333;">Hola {destinatario_nombre},</h2>
        <p>Te invitamos a participar en nuestra encuesta: <strong>{nombre_campana}</strong>.</p>
        <p>Tu opinión es muy importante para {nombre_empresa}. La encuesta solo tomará unos minutos de tu tiempo.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{url_encuesta}" style="background-color: #4CAF50; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Responder Encuesta
            </a>
        </div>
        <p>Si el botón no funciona, puedes copiar y pegar este enlace en tu navegador:</p>
        <p style="word-break: break-all; font-size: 12px;">{url_encuesta}</p>
        <p>El enlace estará activo por {settings.SURVEY_LINK_EXPIRY_DAYS} días.</p>
    </div>
    """
    
    text_content = f"""
    Hola {destinatario_nombre},
    Te invitamos a participar en nuestra encuesta: {nombre_campana}.
    Para responder, visita: {url_encuesta}
    """
    
    return await _send_mail(destinatario_email, destinatario_nombre, asunto, html_content, text_content)


async def enviar_email_terminos(
    destinatario_email: str,
    destinatario_nombre: str,
    url_terminos: str
) -> bool:
    asunto = "Gracias por aceptar los Términos y Condiciones - SurveySaaS"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <h2 style="color: #1e293b; margin-top: 0;">Hola {destinatario_nombre},</h2>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">
            Te confirmamos que has aceptado formalmente los <strong>Términos y Condiciones de Uso</strong> de la plataforma <strong>SurveySaaS</strong>.
        </p>
        <p style="color: #475569; font-size: 14px; line-height: 1.6;">
            Puedes consultar y revisar los términos actualizados en cualquier momento a través del siguiente enlace oficial:
        </p>
        <div style="text-align: center; margin: 25px 0;">
            <a href="{url_terminos}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">
                Ver Términos y Condiciones
            </a>
        </div>
        <p style="color: #94a3b8; font-size: 12px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
            Este es un correo automático de verificación emitido por Desesoft SRL • Manzana 40, Santa Cruz de la Sierra, Bolivia.
        </p>
    </div>
    """
    text_content = f"""
    Hola {destinatario_nombre},
    Confirmamos que has aceptado los Términos y Condiciones de SurveySaaS.
    Puedes consultarlos en: {url_terminos}
    """
    return await _send_mail(destinatario_email, destinatario_nombre, asunto, html_content, text_content)


async def enviar_email_privacidad(
    destinatario_email: str,
    destinatario_nombre: str,
    url_privacidad: str
) -> bool:
    asunto = "Gracias por aceptar nuestra Política de Privacidad - SurveySaaS"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <h2 style="color: #1e293b; margin-top: 0;">Hola {destinatario_nombre},</h2>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">
            Te confirmamos que has aceptado nuestra <strong>Política de Privacidad y Tratamiento de Datos</strong> en <strong>SurveySaaS</strong>.
        </p>
        <p style="color: #475569; font-size: 14px; line-height: 1.6;">
            Tus datos personales y la información de tus encuestas se gestionan bajo estándares internacionales de encriptación y aislamiento por organización.
        </p>
        <div style="text-align: center; margin: 25px 0;">
            <a href="{url_privacidad}" style="background-color: #4f46e5; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">
                Consultar Política de Privacidad
            </a>
        </div>
        <p style="color: #94a3b8; font-size: 12px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
            Deseosoft SRL • Santa Cruz de la Sierra, Bolivia.
        </p>
    </div>
    """
    text_content = f"""
    Hola {destinatario_nombre},
    Confirmamos que has aceptado nuestra Política de Privacidad en SurveySaaS.
    Puedes consultarla en: {url_privacidad}
    """
    return await _send_mail(destinatario_email, destinatario_nombre, asunto, html_content, text_content)


async def enviar_email_bienvenida(
    destinatario_email: str,
    destinatario_nombre: str,
    url_verificacion: str,
    url_software: str
) -> bool:
    asunto = "¡Bienvenido a SurveySaaS! Activa tu cuenta y accede al software"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <div style="text-align: center; margin-bottom: 20px;">
            <span style="font-size: 32px;">🚀</span>
            <h2 style="color: #1e293b; margin: 10px 0 5px;">¡Bienvenido a SurveySaaS!</h2>
            <p style="color: #64748b; font-size: 14px; margin: 0;">Plataforma de Encuestas Multicanal e Inteligencia Artificial</p>
        </div>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">
            Hola <strong>{destinatario_nombre}</strong>, estamos encantados de que formes parte de nuestra comunidad.
        </p>
        <p style="color: #475569; font-size: 14px; line-height: 1.6;">
            Para activar tu acceso oficial y validar tu dirección de correo, haz clic en el siguiente botón:
        </p>
        <div style="text-align: center; margin: 25px 0;">
            <a href="{url_verificacion}" style="background-color: #059669; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 15px; display: inline-block;">
                Activar Cuenta y Acceder al Software
            </a>
        </div>
        <p style="color: #64748b; font-size: 13px;">
            Enlace directo al software: <a href="{url_software}" style="color: #2563eb;">{url_software}</a>
        </p>
        <p style="color: #94a3b8; font-size: 12px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
            Si no solicitaste esta cuenta, puedes desestimar este mensaje.
        </p>
    </div>
    """
    text_content = f"""
    ¡Bienvenido a SurveySaaS, {destinatario_nombre}!
    Para activar tu cuenta y acceder al software, visita: {url_verificacion}
    Acceso directo: {url_software}
    """
    return await _send_mail(destinatario_email, destinatario_nombre, asunto, html_content, text_content)


async def enviar_email_verificacion(
    destinatario_email: str,
    destinatario_nombre: str,
    url_verificacion: str
) -> bool:
    asunto = "Verifica tu cuenta en SurveySaaS"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 5px;">
        <h2 style="color: #333;">Hola {destinatario_nombre},</h2>
        <p>Gracias por registrarte en SurveySaaS. Por favor verifica tu correo haciendo clic en el siguiente botón:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{url_verificacion}" style="background-color: #4CAF50; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Verificar mi cuenta
            </a>
        </div>
        <p>Si el botón no funciona, copia y pega este enlace en tu navegador:</p>
        <p style="word-break: break-all; font-size: 12px;">{url_verificacion}</p>
    </div>
    """

    text_content = f"""
    Hola {destinatario_nombre},
    Gracias por registrarte en SurveySaaS. Por favor verifica tu correo visitando: {url_verificacion}
    """

    return await _send_mail(destinatario_email, destinatario_nombre, asunto, html_content, text_content)


async def enviar_email_recuperacion_contrasena(
    destinatario_email: str,
    destinatario_nombre: str,
    url_reset: str
) -> bool:
    asunto = "Restablece tu contraseña - SurveySaaS"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 5px;">
        <h2 style="color: #333;">Hola {destinatario_nombre},</h2>
        <p>Hemos recibido una solicitud para restablecer tu contraseña en SurveySaaS.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{url_reset}" style="background-color: #2563EB; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Restablecer contraseña
            </a>
        </div>
        <p>Si el botón no funciona, copia y pega este enlace en tu navegador:</p>
        <p style="word-break: break-all; font-size: 12px;">{url_reset}</p>
    </div>
    """

    text_content = f"""
    Hola {destinatario_nombre},
    Recibimos una solicitud para restablecer tu contraseña.
    Para restablecer tu contraseña, visita: {url_reset}
    """

    return await _send_mail(destinatario_email, destinatario_nombre, asunto, html_content, text_content)
