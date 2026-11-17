# tests/test_pagofacil.py
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from app.models.suscriptor import Suscriptor
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor, PagoSuscriptor
from app.models.pagofacil import PagoFacilTransaccion

def setup_test_empresa_and_plan(db_session):
    empresa_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    # 1. Suscriptor
    sus = db_session.query(Suscriptor).filter_by(id=empresa_id).first()
    if not sus:
        sus = Suscriptor(
            id=empresa_id,
            nombre="Empresa Bolivia SRL",
            email="empresa_bolivia@test.com",
            telefono="77123456",
            password_hash="fake_hash_123",
            rol_id=1,
            estado="inactivo"
        )
        db_session.add(sus)
        db_session.flush()

    # 2. Plan Profesional
    plan = db_session.query(PlanSuscripcion).filter_by(nombre="Profesional").first()
    if not plan:
        plan = PlanSuscripcion(
            nombre="Profesional",
            precio_mensual=29.99,
            descripcion="Plan profesional con IA",
            activo=True
        )
        db_session.add(plan)
        db_session.flush()

    db_session.commit()
    return empresa_id, plan.id

def test_pagofacil_metodos_habilitados(client):
    """Verifica que el catálogo de métodos QR habilitados responda correctamente."""
    # Prueba ruta /pagofacil/metodos
    res1 = client.get("/pagofacil/metodos")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["error"] == 0
    assert data1["status"] == 2006
    assert isinstance(data1["values"], list)
    assert len(data1["values"]) > 0
    assert "paymentMethodId" in data1["values"][0]

    # Prueba ruta alias /subscription/pagofacil/metodos
    res2 = client.get("/subscription/pagofacil/metodos")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["error"] == 0
    assert data2["status"] == 2006

def test_pagofacil_generar_qr_exitoso(client, db_session, empresa_headers):
    """Verifica la generación de un código QR y registro de la orden."""
    empresa_id, plan_id = setup_test_empresa_and_plan(db_session)

    payload = {
        "plan_id": plan_id,
        "document_type": 1,
        "document_id": "4891234",
        "phone_number": "77123456"
    }

    res = client.post("/pagofacil/generar-qr", json=payload, headers=empresa_headers)
    assert res.status_code == 201
    data = res.json()

    assert data["success"] is True
    assert data["payment_number"].startswith("PF-")
    assert data["status"] == "pendiente"
    assert data["monto"] > 0
    assert data["moneda"] == "BOB"
    assert data["plan_nombre"] == "Profesional"
    assert data["qr_base64"] is not None
    assert len(data["qr_base64"]) > 10

    # Verificar persistencia en base de datos
    tx = db_session.query(PagoFacilTransaccion).filter_by(payment_number=data["payment_number"]).first()
    assert tx is not None
    assert tx.suscriptor_id == empresa_id
    assert tx.plan_id == plan_id
    assert tx.estado == "pendiente"
    assert float(tx.monto) == data["monto"]

def test_pagofacil_consultar_estado_pendiente(client, db_session, empresa_headers):
    """Verifica que el endpoint de polling retorne pendiente mientras no se haya pagado."""
    empresa_id, plan_id = setup_test_empresa_and_plan(db_session)

    gen_res = client.post("/subscription/pagofacil/generar-qr", json={"plan_id": plan_id}, headers=empresa_headers)
    assert gen_res.status_code == 201
    payment_number = gen_res.json()["payment_number"]

    # Consultar estado
    query_res = client.get(f"/pagofacil/consultar/{payment_number}")
    assert query_res.status_code == 200
    data = query_res.json()

    assert data["success"] is True
    assert data["payment_number"] == payment_number
    assert data["estado"] == "pendiente"
    assert data["pagado"] is False

def test_pagofacil_callback_exitoso_y_activacion(client, db_session, empresa_headers):
    """
    Verifica el ciclo completo de pago vía webhook Callback de PagoFácil:
    1. Genera QR
    2. Recibe webhook POST con PedidoID
    3. Responde con el formato JSON esperado por PagoFácil
    4. Activa la membresía del suscriptor
    5. Registra el pago en el historial
    """
    empresa_id, plan_id = setup_test_empresa_and_plan(db_session)

    # 1. Generar orden QR
    gen_res = client.post("/pagofacil/generar-qr", json={"plan_id": plan_id}, headers=empresa_headers)
    payment_number = gen_res.json()["payment_number"]

    # 2. Simular llamada de Callback desde el servidor de PagoFácil
    callback_payload = {
        "PedidoID": payment_number,
        "Fecha": "2026-11-17",
        "Hora": "10:45:00",
        "MetodoPago": "QR Simple BCP",
        "Estado": "COMPLETADO"
    }

    cb_res = client.post("/pagofacil/callback", json=callback_payload)
    assert cb_res.status_code == 200
    cb_data = cb_res.json()

    # Formato oficial esperado por PagoFácil
    assert cb_data["error"] == 0
    assert cb_data["status"] == 1
    assert cb_data["values"] is True

    # 3. Validar cambios en la base de datos
    db_session.expire_all()
    tx = db_session.query(PagoFacilTransaccion).filter_by(payment_number=payment_number).first()
    assert tx.estado == "completado"
    assert tx.callback_payload is not None
    assert tx.callback_payload["PedidoID"] == payment_number

    suscriptor = db_session.query(Suscriptor).filter_by(id=empresa_id).first()
    assert suscriptor.estado == "activo"

    suscripcion = db_session.query(SuscripcionSuscriptor).filter_by(suscriptor_id=empresa_id, estado="activo").first()
    assert suscripcion is not None
    assert suscripcion.plan_id == plan_id

    pago = db_session.query(PagoSuscriptor).filter_by(suscriptor_id=empresa_id, referencia_stripe=f"PF:{payment_number}").first()
    assert pago is not None
    assert pago.estado == "completado"
    assert "QR Simple BCP" in pago.metodo_pago

    # 4. Verificar que la consulta posterior de la transacción devuelva pagado=True
    query_res = client.get(f"/pagofacil/consultar/{payment_number}")
    assert query_res.status_code == 200
    assert query_res.json()["pagado"] is True
    assert query_res.json()["estado"] == "completado"

def test_pagofacil_polling_auto_activate_when_api_confirms(client, db_session, empresa_headers):
    """
    Verifica que si el cliente consulta /consultar/{payment_number} y PagoFácil
    reporta que el QR ya fue pagado, el sistema activa automáticamente la suscripción.
    """
    empresa_id, plan_id = setup_test_empresa_and_plan(db_session)

    gen_res = client.post("/pagofacil/generar-qr", json={"plan_id": plan_id}, headers=empresa_headers)
    payment_number = gen_res.json()["payment_number"]

    # Simular que PagoFácil responde en /query-transaction con paymentStatus=2 (Pagado)
    with patch("app.services.pagofacil_service.pagofacil_client.query_transaction", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "pagofacilTransactionId": 998877,
            "companyTransactionId": payment_number,
            "paymentMethodId": 1,
            "paymentStatus": 2, # Pagado
            "amount": "208.73",
            "currencyId": 2,
            "paymentDate": "2026-11-17",
            "paymentTime": "11:00:00"
        }

        poll_res = client.get(f"/pagofacil/consultar/{payment_number}")
        assert poll_res.status_code == 200
        data = poll_res.json()
        assert data["pagado"] is True
        assert data["estado"] == "completado"

        # Verificar que la suscripción se haya activado
        db_session.expire_all()
        sub = db_session.query(SuscripcionSuscriptor).filter_by(suscriptor_id=empresa_id, estado="activo").first()
        assert sub is not None

def test_pagofacil_callback_pedido_inexistente(client):
    """Verifica que un callback con PedidoID no registrado retorne error estructurado."""
    callback_payload = {
        "PedidoID": "INEXISTENTE-9999",
        "Estado": "COMPLETADO"
    }
    res = client.post("/pagofacil/callback", json=callback_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["error"] == 1
    assert data["status"] == 0
    assert data["values"] is False

def test_pagofacil_listar_transacciones_suscriptor(client, db_session, empresa_headers):
    """Verifica el endpoint de historial de transacciones de la empresa."""
    empresa_id, plan_id = setup_test_empresa_and_plan(db_session)

    client.post("/pagofacil/generar-qr", json={"plan_id": plan_id}, headers=empresa_headers)

    res = client.get("/pagofacil/transacciones", headers=empresa_headers)
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert len(items) > 0
    assert "payment_number" in items[0]
    assert "monto" in items[0]
    assert "estado" in items[0]
