import pytest
from uuid import UUID
from unittest.mock import AsyncMock, patch
from app.models.contacto import Contacto
from app.core.rate_limit import _request_history

def test_contacto_guarda_origen_y_tipo_y_muestra_en_email(client, db_session):
    _request_history.clear()
    """
    Verifica que POST /contacto:
    1. Acepte y guarde en BD origen ('corporativo' o 'producto') y tipo ('comercial', 'soporte técnico' o 'derechos sobre datos').
    2. Los muestre en el correo que se envía.
    3. Registre la consulta en la base de datos.
    """
    with patch("app.routers.contacto_router._send_mail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # 1. Caso Corporativo Comercial
        res_corp = client.post(
            "/contacto",
            json={
                "nombre": "Carlos Corporativo",
                "email": "carlos@empresa.bo",
                "empresa": "Desesoft Partner",
                "origen": "corporativo",
                "tipo": "comercial",
                "mensaje": "Interesado en cotización de plan Enterprise para 100 usuarios.",
            }
        )
        assert res_corp.status_code == 201
        data_corp = res_corp.json()
        assert data_corp["success"] is True
        contacto_id_corp = data_corp["contacto_id"]

        # Verificar en base de datos
        db_contacto_corp = db_session.query(Contacto).filter(Contacto.id == UUID(contacto_id_corp)).first()
        assert db_contacto_corp is not None
        assert db_contacto_corp.origen == "corporativo"
        assert db_contacto_corp.tipo == "comercial"
        assert db_contacto_corp.email == "carlos@empresa.bo"

        # Verificar correo despachado
        args_corp = mock_send.call_args[0]
        asunto_corp = args_corp[2]
        html_corp = args_corp[3]
        text_corp = args_corp[4]
        assert "corporativo" in asunto_corp.lower() or "corporativo" in html_corp.lower()
        assert "comercial" in asunto_corp.lower() or "comercial" in html_corp.lower()
        assert "carlos@empresa.bo" in html_corp

        # 2. Caso Producto Soporte Técnico
        mock_send.reset_mock()
        res_soporte = client.post(
            "/contacto",
            json={
                "nombre": "Ana Soporte",
                "email": "ana@cliente.com",
                "origen": "producto",
                "tipo": "soporte técnico",
                "mensaje": "Error en sincronización offline de encuestas.",
            }
        )
        assert res_soporte.status_code == 201
        contacto_id_soporte = res_soporte.json()["contacto_id"]

        db_contacto_soporte = db_session.query(Contacto).filter(Contacto.id == UUID(contacto_id_soporte)).first()
        assert db_contacto_soporte is not None
        assert db_contacto_soporte.origen == "producto"
        assert db_contacto_soporte.tipo == "soporte_tecnico"

        args_soporte = mock_send.call_args[0]
        html_soporte = args_soporte[3]
        assert "producto" in html_soporte.lower()
        assert "soporte técnico" in html_soporte.lower()

        # 3. Caso Derechos sobre datos
        mock_send.reset_mock()
        res_derechos = client.post(
            "/contacto",
            json={
                "nombre": "Roberto Datos",
                "email": "roberto@privacidad.org",
                "origen": "producto",
                "tipo": "derechos sobre datos",
                "mensaje": "Solicito la supresión de mis datos conforme a la política ARCO.",
            }
        )
        assert res_derechos.status_code == 201
        contacto_id_derechos = res_derechos.json()["contacto_id"]

        db_contacto_derechos = db_session.query(Contacto).filter(Contacto.id == UUID(contacto_id_derechos)).first()
        assert db_contacto_derechos is not None
        assert db_contacto_derechos.origen == "producto"
        assert db_contacto_derechos.tipo == "derechos_datos"

        args_derechos = mock_send.call_args[0]
        html_derechos = args_derechos[3]
        assert "derechos sobre datos" in html_derechos.lower()

