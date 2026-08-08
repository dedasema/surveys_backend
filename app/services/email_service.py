try:
    import aiosmtplib
except Exception:
    aiosmtplib = None

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import asyncio
import smtplib
from app.core.config import settings

logger = logging.getLogger(__name__)

async def _send_mail_helper(message: MIMEMultipart) -> None:
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise ValueError("SMTP_USERNAME o SMTP_PASSWORD no están configurados")

    clean_password = settings.SMTP_PASSWORD.replace(" ", "").strip()

    if aiosmtplib is not None:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_SERVER,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=clean_password,
            start_tls=(settings.SMTP_PORT == 587),
            use_tls=(settings.SMTP_PORT == 465),
            timeout=15.0
        )
    else:
        def _sync_send():
            if settings.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15.0) as server:
                    server.login(settings.SMTP_USERNAME, clean_password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15.0) as server:
                    server.starttls()
                    server.login(settings.SMTP_USERNAME, clean_password)
                    server.send_message(message)

        await asyncio.to_thread(_sync_send)


async def enviar_email(
    destinatario_email: str,
    destinatario_nombre: str,
    asunto: str,
    nombre_campana: str,
    nombre_empresa: str, 
    url_encuesta: str
) -> bool:
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = asunto
        message["From"] = f"{nombre_empresa} <{settings.SMTP_USERNAME}>"
        message["To"] = f"{destinatario_nombre} <{destinatario_email}>"
        
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
        
        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))
        
        await _send_mail_helper(message)
        logger.info(f"Email enviado a {destinatario_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error enviando email: {str(e)}")
        return False


async def enviar_email_verificacion(
    destinatario_email: str,
    destinatario_nombre: str,
    url_verificacion: str
) -> bool:
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = "Verifica tu cuenta en SurveySaaS"
        message["From"] = f"SurveySaaS <{settings.SMTP_USERNAME}>"
        message["To"] = f"{destinatario_nombre} <{destinatario_email}>"

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

        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))

        await _send_mail_helper(message)
        logger.info(f"Correo de verificación enviado a {destinatario_email}")
        return True

    except Exception as e:
        logger.error(f"Error enviando email de verificación: {str(e)}")
        return False


async def enviar_email_recuperacion_contrasena(
    destinatario_email: str,
    destinatario_nombre: str,
    url_reset: str
) -> bool:
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = "Restablece tu contraseña - SurveySaaS"
        message["From"] = f"SurveySaaS <{settings.SMTP_USERNAME}>"
        message["To"] = f"{destinatario_nombre} <{destinatario_email}>"

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

        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))

        await _send_mail_helper(message)
        logger.info(f"Correo de recuperación enviado a {destinatario_email}")
        return True

    except Exception as e:
        logger.error(f"Error enviando email de recuperación: {str(e)}")
        return False
