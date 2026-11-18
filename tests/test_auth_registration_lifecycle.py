# tests/test_auth_registration_lifecycle.py
import pytest
from unittest.mock import patch, AsyncMock
from app.models.suscriptor import Suscriptor
from app.models.catalogos import Rol

def test_registration_commercial_email_and_pending_guard(client, db_session):
    """
    Verifica que:
    1. Se acepten emails personales/comerciales como @gmail.com sin restricciones.
    2. El suscriptor quede en estado 'pendiente' en la base de datos tras request-registration.
    3. El intento de login previo a la verificación sea rechazado con 403 Forbidden y mensaje explicativo.
    """
    email_test = "empresanueva@gmail.com"
    password_test = "PasswordSeguro123!"

    # Limpiar si existía
    db_session.query(Suscriptor).filter_by(email=email_test).delete()
    db_session.commit()

    with patch("app.services.email_service._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # 1. Registrar empresa con @gmail.com
        res_reg = client.post(
            "/auth/request-registration",
            json={
                "nombre": "Empresa Gmail SRL",
                "email": email_test,
                "telefono": "+59177123456",
                "password": password_test
            }
        )
        assert res_reg.status_code == 200
        assert "3 correos" in res_reg.json()["message"]

        # 2. Comprobar que en BD el estado es 'pendiente'
        sus = db_session.query(Suscriptor).filter_by(email=email_test).first()
        assert sus is not None
        assert sus.estado.lower() == "pendiente"

        # 3. Intentar Login ANTES de verificar por correo -> Debe devolver 403 Forbidden
        res_login = client.post(
            "/auth/login",
            json={
                "email": email_test,
                "password": password_test
            }
        )
        assert res_login.status_code == 403
        assert "Debes verificar tu correo electrónico antes de ingresar" in res_login.json()["detail"]


def test_verify_registration_activates_and_enables_login(client, db_session):
    """
    Verifica que:
    1. Al hacer clic en el enlace de activación (/auth/verificar-registro o /auth/verify-registration),
       el estado pase a 'activo'.
    2. Posterior a la activación, el login con las mismas credenciales devuelva 200 OK y access_token.
    """
    email_test = "activacion@outlook.com"
    password_test = "SuperPassword123!"

    db_session.query(Suscriptor).filter_by(email=email_test).delete()
    db_session.commit()

    with patch("app.services.email_service._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # Registrar
        client.post(
            "/auth/request-registration",
            json={
                "nombre": "Empresa Outlook SA",
                "email": email_test,
                "telefono": "78945612",
                "password": password_test
            }
        )

        # Extraer el token generado simulando el enlace enviado en el correo
        import jwt
        from datetime import datetime, timezone, timedelta
        from app.core.config import settings

        token_data = {
            "sub": email_test,
            "nombre": "Empresa Outlook SA",
            "telefono": "78945612",
            "exp": datetime.now(timezone.utc) + timedelta(hours=24)
        }
        test_token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        # Activar mediante endpoint oficial en español
        res_verify = client.get(f"/auth/verificar-registro?token={test_token}")
        assert res_verify.status_code == 200
        assert res_verify.json()["estado"] == "activo"

        # Verificar en base de datos
        sus = db_session.query(Suscriptor).filter_by(email=email_test).first()
        assert sus is not None
        assert sus.estado.lower() == "activo"

        # Intentar Login AHORA -> Debe ser exitoso (200 OK)
        res_login = client.post(
            "/auth/login",
            json={
                "email": email_test,
                "password": password_test
            }
        )
        assert res_login.status_code == 200
        data_login = res_login.json()
        assert "access_token" in data_login
        assert data_login["token_type"] == "bearer"


def test_contacto_and_leads_endpoint(client):
    """
    Verifica la captura de leads del formulario de la Landing Page en /contacto y /leads.
    """
    with patch("app.services.email_service._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # Prueba en /contacto
        res_c = client.post(
            "/contacto",
            json={
                "nombre": "Juan Pérez",
                "email": "juan.perez@empresa.com",
                "empresa": "TechCorp Bolivia",
                "mensaje": "Quisiera agendar una demo comercial para 50 encuestadores."
            }
        )
        assert res_c.status_code == 201
        assert res_c.json()["success"] is True

        # Prueba en /leads (alias)
        res_l = client.post(
            "/leads",
            json={
                "nombre": "María García",
                "email": "maria@startup.io",
                "empresa": "Startup Latam",
                "mensaje": "Consulta sobre integración por API."
            }
        )
        assert res_l.status_code == 201
        assert res_l.json()["success"] is True
