# app/services/pagofacil_service.py
import os
import uuid
import time
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.pagofacil import PagoFacilTransaccion
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor, PagoSuscriptor
from app.models.suscriptor import Suscriptor
from app.schemas.pagofacil import (
    GenerarQRPayload,
    GenerarQRResponse,
    ConsultarTransaccionResponse,
    PagoFacilCallbackPayload,
    PagoFacilCallbackResponse,
    MetodoHabilitadoItem,
    MetodosHabilitadosResponse
)
from app.services.audit_service import registrar_auditoria

logger = logging.getLogger(__name__)

class PagoFacilClient:
    """
    Cliente HTTP asíncrono para la API v2 de PagoFácil Bolivia (Método QR).
    Implementa autenticación, caché de token y manejo de endpoints oficiales.
    """
    def __init__(self):
        self.base_url = settings.PAGOFACIL_BASE_URL.rstrip("/")
        self._cached_token: Optional[str] = None
        self._token_expiry_timestamp: float = 0.0

    @property
    def token_service(self) -> str:
        return settings.pagofacil_token_service

    @property
    def token_secret(self) -> str:
        return settings.pagofacil_token_secret

    def is_configured(self) -> bool:
        return bool(self.token_service and self.token_secret and "dummy" not in self.token_service.lower())

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Obtiene un accessToken llamando a POST /login.
        Reutiliza el token en memoria si aún es válido.
        """
        now = time.time()
        if not force_refresh and self._cached_token and now < self._token_expiry_timestamp:
            return self._cached_token

        if not self.is_configured():
            # Token simulado para desarrollo/pruebas locales si no hay credenciales reales
            self._cached_token = f"sim_token_pagofacil_{uuid.uuid4().hex}"
            self._token_expiry_timestamp = now + 3600
            return self._cached_token

        login_url = f"{self.base_url}/login"
        headers = {
            "tcTokenSecret": self.token_secret,
            "tcTokenService": self.token_service,
            "Response-Language": "es"
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                res = await client.post(login_url, headers=headers)
                if res.status_code != 200:
                    logger.error(f"Error en PagoFacil /login ({res.status_code}): {res.text}")
                    raise RuntimeError(f"Error de autenticación PagoFacil: {res.text}")

                data = res.json()
                if data.get("error") != 0 or data.get("status") != 1:
                    raise RuntimeError(f"PagoFacil login rechazado: {data.get('message')}")

                values = data.get("values", {})
                token = values.get("accessToken")
                expires_in_minutes = float(values.get("expiresInMinutes", 60.0))

                if not token:
                    raise RuntimeError("PagoFacil no devolvió accessToken en respuesta de login")

                self._cached_token = token
                # Margen de seguridad de 5 minutos antes de expirar
                self._token_expiry_timestamp = now + max((expires_in_minutes - 5) * 60, 60)
                return self._cached_token

            except httpx.RequestError as exc:
                logger.error(f"Falla de conexión conectando a PagoFacil /login: {exc}")
                raise RuntimeError(f"No se pudo conectar al servidor de PagoFacil: {str(exc)}")

    async def list_enabled_services(self) -> List[Dict[str, Any]]:
        """
        Consulta lista de métodos de pago QR habilitados (POST /list-enabled-services).
        """
        if not self.is_configured():
            return [
                {
                    "paymentMethodId": 1,
                    "paymentMethodName": "QR PagoFácil (Simulado)",
                    "currencyName": "BOB",
                    "maxAmountPerDay": 10000.0,
                    "maxAmountPerTransaction": 5000.0
                }
            ]

        token = await self.get_access_token()
        url = f"{self.base_url}/list-enabled-services"
        headers = {
            "Authorization": f"Bearer {token}",
            "Response-Language": "es"
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, headers=headers)
            if res.status_code != 200:
                raise RuntimeError(f"Error al listar métodos habilitados ({res.status_code}): {res.text}")
            data = res.json()
            return data.get("values", [])

    async def generate_qr(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera un código QR en PagoFácil (POST /generate-qr).
        """
        if not self.is_configured():
            # Generador de QR simulado para testing/desarrollo
            dummy_qr_svg = (
                f"<svg xmlns='http://www.w3.org/2000/svg' width='250' height='250' viewBox='0 0 250 250'>"
                f"<rect width='250' height='250' fill='#ffffff'/>"
                f"<text x='50%' y='45%' text-anchor='middle' font-family='sans-serif' font-size='16' fill='#0284c7'>QR PagoFácil Simulado</text>"
                f"<text x='50%' y='60%' text-anchor='middle' font-family='sans-serif' font-size='14' fill='#334155'>Monto: {payload.get('amount')} BOB</text>"
                f"<text x='50%' y='75%' text-anchor='middle' font-family='sans-serif' font-size='10' fill='#64748b'>Orden: {payload.get('paymentNumber')}</text>"
                f"</svg>"
            )
            dummy_b64 = base64.b64encode(dummy_qr_svg.encode("utf-8")).decode("utf-8")
            return {
                "transactionId": f"pf_tx_{uuid.uuid4().hex[:12]}",
                "paymentMethodTransactionId": payload.get("paymentNumber"),
                "status": 1,
                "expirationDate": (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                "qrBase64": dummy_b64,
                "checkoutUrl": f"https://checkout.pagofacil.com.bo/sim/{payload.get('paymentNumber')}",
                "deepLink": f"pagofacil://qr/{payload.get('paymentNumber')}",
                "qrContentUrl": f"https://masterqr.pagofacil.com.bo/qr/{payload.get('paymentNumber')}",
                "universalUrl": f"https://pagofacil.com.bo/pay/{payload.get('paymentNumber')}"
            }

        token = await self.get_access_token()
        url = f"{self.base_url}/generate-qr"
        headers = {
            "Authorization": f"Bearer {token}",
            "Response-Language": "es"
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Error generando QR en PagoFácil ({res.status_code}): {res.text}")
            data = res.json()
            if data.get("error") != 0:
                raise RuntimeError(f"PagoFácil rechazó generar QR: {data.get('message')}")
            return data.get("values", {})

    async def query_transaction(self, company_transaction_id: str, pagofacil_transaction_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Consulta estado actual de una transacción en PagoFácil (POST /query-transaction).
        """
        if not self.is_configured():
            return {
                "pagofacilTransactionId": pagofacil_transaction_id or "sim_pf_123",
                "companyTransactionId": company_transaction_id,
                "paymentMethodId": 1,
                "paymentStatus": 1, # 1: Pendiente
                "amount": "0.00",
                "currencyId": 2,
                "paymentDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "paymentTime": datetime.now(timezone.utc).strftime("%H:%M:%S")
            }

        token = await self.get_access_token()
        url = f"{self.base_url}/query-transaction"
        headers = {
            "Authorization": f"Bearer {token}",
            "Response-Language": "es"
        }
        body: Dict[str, Any] = {"companyTransactionId": company_transaction_id}
        if pagofacil_transaction_id:
            body["pagofacilTransactionId"] = pagofacil_transaction_id

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, headers=headers, json=body)
            if res.status_code != 200:
                raise RuntimeError(f"Error consultando transacción ({res.status_code}): {res.text}")
            data = res.json()
            return data.get("values", {})

pagofacil_client = PagoFacilClient()


# ─────────────────── Lógica de Negocio y Base de Datos ─────────────────── #

TIPO_CAMBIO_BOB_USD = 6.96

def calcular_monto_bob(plan: PlanSuscripcion, custom_monto: Optional[float] = None) -> float:
    """Calcula el monto en Bolivianos (BOB) para el plan."""
    if custom_monto is not None and custom_monto > 0:
        return round(float(custom_monto), 2)
    precio_usd = float(plan.precio_mensual or 0.0)
    monto_bob = round(precio_usd * TIPO_CAMBIO_BOB_USD, 2)
    # Si el plan es gratuito, permitir monto mínimo de prueba si se requiere
    return max(monto_bob, 0.0)

async def crear_orden_qr(
    db: Session,
    suscriptor_id: UUID,
    payload: GenerarQRPayload
) -> GenerarQRResponse:
    """
    Inicia el flujo de cobro con PagoFácil:
    1. Verifica existencia de suscriptor y plan.
    2. Registra la transacción en estado 'pendiente'.
    3. Llama a PagoFácil para generar el QR oficial.
    4. Almacena el QR (base64) y URLs en BD.
    5. Retorna la respuesta para el cliente.
    """
    suscriptor = db.query(Suscriptor).filter_by(id=suscriptor_id).first()
    if not suscriptor:
        raise ValueError("Suscriptor no encontrado")

    plan = db.query(PlanSuscripcion).filter_by(id=payload.plan_id).first()
    if not plan:
        raise ValueError("Plan de suscripción no encontrado")

    monto_bob = calcular_monto_bob(plan, payload.monto)
    if monto_bob <= 0:
        # Si el plan es gratuito ($0 USD), activar directamente sin QR
        suscripcion = SuscripcionSuscriptor(
            suscriptor_id=suscriptor.id,
            plan_id=plan.id,
            inicia_en=datetime.now(timezone.utc),
            expira_en=datetime.now(timezone.utc) + timedelta(days=30),
            estado="activo"
        )
        suscriptor.estado = "activo"
        db.add(suscripcion)
        db.commit()
        return GenerarQRResponse(
            success=True,
            payment_number=f"GRATIS-{uuid.uuid4().hex[:8]}",
            status="completado",
            monto=0.0,
            moneda="BOB",
            plan_nombre=plan.nombre,
            checkout_url=f"{settings.clean_frontend_url}/dashboard-suscriptor/planes/success"
        )

    # Identificador único de transacción del comercio
    payment_number = f"PF-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # Callback URL: usar la configurada o la default del backend
    callback_url = payload.callback_url or settings.PAGOFACIL_CALLBACK_URL
    if not callback_url:
        api_base = settings.API_BASE_URL.rstrip("/")
        callback_url = f"{api_base}/subscription/pagofacil/callback"

    # 1. Crear registro en BD en estado 'pendiente'
    nueva_tx = PagoFacilTransaccion(
        payment_number=payment_number,
        suscriptor_id=suscriptor.id,
        plan_id=plan.id,
        monto=monto_bob,
        moneda=payload.moneda or "BOB",
        tipo_cambio=TIPO_CAMBIO_BOB_USD,
        estado="pendiente"
    )
    db.add(nueva_tx)
    db.commit()
    db.refresh(nueva_tx)

    # 2. Construir payload para PagoFácil
    client_name = payload.client_name or suscriptor.nombre or "Cliente"
    client_phone = payload.phone_number or getattr(suscriptor, "telefono", "") or "70000000"
    client_email = payload.email or suscriptor.email or "cliente@surveysaas.com"
    doc_id = payload.document_id or "0"

    pf_request_payload = {
        "paymentMethod": 1,  # Método QR (1)
        "clientName": client_name,
        "documentType": payload.document_type or 1,
        "documentId": doc_id,
        "phoneNumber": client_phone,
        "email": client_email,
        "paymentNumber": payment_number,
        "amount": monto_bob,
        "currency": 2,  # 2: BOB (Bolivianos)
        "clientCode": str(suscriptor.id),
        "callbackUrl": callback_url,
        "orderDetail": [
            {
                "serial": 1,
                "product": f"Suscripción Mensual - {plan.nombre}",
                "quantity": 1,
                "price": monto_bob,
                "discount": 0,
                "total": monto_bob
            }
        ]
    }

    # 3. Invocar API de PagoFácil
    try:
        qr_data = await pagofacil_client.generate_qr(pf_request_payload)

        # 4. Actualizar registro con datos devueltos por PagoFácil
        nueva_tx.pagofacil_transaction_id = str(qr_data.get("transactionId", ""))
        nueva_tx.qr_base64 = qr_data.get("qrBase64")
        nueva_tx.checkout_url = qr_data.get("checkoutUrl")
        nueva_tx.deep_link = qr_data.get("deepLink")
        nueva_tx.qr_content_url = qr_data.get("qrContentUrl")
        nueva_tx.universal_url = qr_data.get("universalUrl")
        
        exp_date_str = qr_data.get("expirationDate")
        if exp_date_str:
            try:
                nueva_tx.fecha_expiracion = datetime.strptime(exp_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                nueva_tx.fecha_expiracion = datetime.now(timezone.utc) + timedelta(hours=2)
        else:
            nueva_tx.fecha_expiracion = datetime.now(timezone.utc) + timedelta(hours=2)

        db.commit()

        # Auditoría de generación
        registrar_auditoria(
            db=db,
            accion="GENERAR_QR",
            modulo="PAGOFACIL",
            suscriptor_id=suscriptor.id,
            usuario_email=suscriptor.email,
            entidad_id=payment_number,
            detalles={"plan": plan.nombre, "monto_bob": monto_bob}
        )

        return GenerarQRResponse(
            success=True,
            payment_number=payment_number,
            transaction_id=nueva_tx.pagofacil_transaction_id,
            status=nueva_tx.estado,
            qr_base64=nueva_tx.qr_base64,
            checkout_url=nueva_tx.checkout_url,
            deep_link=nueva_tx.deep_link,
            qr_content_url=nueva_tx.qr_content_url,
            universal_url=nueva_tx.universal_url,
            expiration_date=exp_date_str,
            monto=monto_bob,
            moneda="BOB",
            plan_nombre=plan.nombre
        )

    except Exception as e:
        nueva_tx.estado = "fallido"
        db.commit()
        logger.error(f"Error generando QR PagoFácil: {e}")
        raise RuntimeError(f"Error generando código QR en PagoFácil: {str(e)}")

def activar_suscripcion_por_pago(
    db: Session,
    transaccion: PagoFacilTransaccion,
    metodo_pago_nombre: str = "PagoFácil QR"
):
    """
    Activa la suscripción del suscriptor y registra el pago tras confirmación exitosa.
    """
    suscriptor = db.query(Suscriptor).filter_by(id=transaccion.suscriptor_id).first()
    plan = db.query(PlanSuscripcion).filter_by(id=transaccion.plan_id).first()

    if not suscriptor or not plan:
        logger.error("No se encontró suscriptor o plan para activar suscripción tras pago")
        return

    # 1. Desactivar suscripciones anteriores activas
    suscripciones_ant = (
        db.query(SuscripcionSuscriptor)
        .filter_by(suscriptor_id=suscriptor.id, estado="activo")
        .all()
    )
    for s in suscripciones_ant:
        s.estado = "cancelado"

    # 2. Crear nueva suscripción activa por 30 días
    ahora = datetime.now(timezone.utc)
    nueva_sub = SuscripcionSuscriptor(
        suscriptor_id=suscriptor.id,
        plan_id=plan.id,
        inicia_en=ahora,
        expira_en=ahora + timedelta(days=30),
        estado="activo",
        stripe_subscription_id=f"pf_{transaccion.payment_number}"
    )
    suscriptor.estado = "activo"
    db.add(nueva_sub)

    # 3. Registrar el pago en el historial de pagos
    pago_record = PagoSuscriptor(
        suscriptor_id=suscriptor.id,
        referencia_stripe=f"PF:{transaccion.payment_number}",
        monto=transaccion.monto,
        moneda=transaccion.moneda.lower(),
        plan_nombre=plan.nombre,
        metodo_pago=metodo_pago_nombre,
        estado="completado"
    )
    db.add(pago_record)

    # 4. Actualizar transacción PagoFácil
    transaccion.estado = "completado"

    db.commit()

    # 5. Auditoría
    registrar_auditoria(
        db=db,
        accion="PAGO_COMPLETADO",
        modulo="PAGOFACIL",
        suscriptor_id=suscriptor.id,
        usuario_email=suscriptor.email,
        entidad_id=transaccion.payment_number,
        detalles={
            "plan": plan.nombre,
            "monto": float(transaccion.monto),
            "moneda": transaccion.moneda,
            "metodo": metodo_pago_nombre
        }
    )

def procesar_callback_pagofacil(
    db: Session,
    payload: PagoFacilCallbackPayload
) -> PagoFacilCallbackResponse:
    """
    Procesa la notificación enviada por PagoFácil a la URL de Callback:
    {
      "PedidoID": "Id_Transaccion_Empresa",
      "Fecha": "Fecha de realización del pago",
      "Hora": "Hora del pago",
      "MetodoPago": "Medio por el que se realizo el pago",
      "Estado": "Estado del pago"
    }
    """
    pedido_id = payload.PedidoID
    transaccion = db.query(PagoFacilTransaccion).filter_by(payment_number=pedido_id).first()

    if not transaccion:
        logger.warning(f"Callback recibido de PagoFácil pero PedidoID no existe en BD: {pedido_id}")
        return PagoFacilCallbackResponse(
            error=1,
            status=0,
            message="Pedido no encontrado en el sistema",
            values=False
        )

    # Guardar payload recibido
    transaccion.callback_payload = payload.model_dump()

    # Evaluar si el estado representa pago exitoso
    estado_val = str(payload.Estado or "").strip().upper()
    metodo = payload.MetodoPago or "PagoFácil QR"

    # Estados típicos de éxito: "COMPLETADO", "PAGADO", "EXITOSO", "1", "2"
    estados_exito = {"COMPLETADO", "PAGADO", "EXITOSO", "APROBADO", "1", "2", "SUCCESS"}
    es_exitoso = estado_val in estados_exito or estado_val == ""  # Si PagoFácil invoca callback post-pago

    if es_exitoso:
        if transaccion.estado != "completado":
            activar_suscripcion_por_pago(db, transaccion, metodo_pago_nombre=f"PagoFácil QR ({metodo})")
        return PagoFacilCallbackResponse(
            error=0,
            status=1,
            message="Pago verificado y suscripción activada exitosamente",
            values=True
        )
    else:
        transaccion.estado = "fallido"
        db.commit()
        return PagoFacilCallbackResponse(
            error=0,
            status=1,
            message="Notificación recibida (estado no completado)",
            values=True
        )

async def consultar_estado_transaccion(
    db: Session,
    payment_number: str
) -> ConsultarTransaccionResponse:
    """
    Consulta el estado de una transacción:
    1. Si en BD ya está 'completado', retorna confirmado.
    2. Si está 'pendiente', consulta en tiempo real a PagoFácil (/query-transaction).
    3. Si PagoFácil confirma pago, activa la suscripción y actualiza BD.
    """
    tx = db.query(PagoFacilTransaccion).filter_by(payment_number=payment_number).first()
    if not tx:
        raise ValueError(f"Transacción {payment_number} no encontrada")

    if tx.estado == "completado":
        return ConsultarTransaccionResponse(
            success=True,
            payment_number=tx.payment_number,
            estado=tx.estado,
            pagado=True,
            monto=float(tx.monto),
            moneda=tx.moneda,
            pagofacil_transaction_id=tx.pagofacil_transaction_id,
            fecha_pago=tx.actualizado_en.isoformat() if tx.actualizado_en else None,
            mensaje="Pago completado exitosamente"
        )

    # Consultar API PagoFácil
    try:
        pf_info = await pagofacil_client.query_transaction(
            company_transaction_id=tx.payment_number,
            pagofacil_transaction_id=tx.pagofacil_transaction_id
        )

        pf_status = pf_info.get("paymentStatus")
        # En PagoFácil, paymentStatus 2 suele ser 'Pagado/Completado'
        # o paymentStatus string 'Pagado'/'Completado'
        status_str = str(pf_status).strip().upper() if pf_status is not None else ""
        if status_str in ["2", "PAGADO", "COMPLETADO", "EXITOSO"]:
            activar_suscripcion_por_pago(db, tx, metodo_pago_nombre="PagoFácil QR")
            return ConsultarTransaccionResponse(
                success=True,
                payment_number=tx.payment_number,
                estado="completado",
                pagado=True,
                monto=float(tx.monto),
                moneda=tx.moneda,
                pagofacil_transaction_id=tx.pagofacil_transaction_id,
                fecha_pago=datetime.now(timezone.utc).isoformat(),
                mensaje="Pago confirmado exitosamente desde PagoFácil"
            )

        return ConsultarTransaccionResponse(
            success=True,
            payment_number=tx.payment_number,
            estado=tx.estado,
            pagado=False,
            monto=float(tx.monto),
            moneda=tx.moneda,
            pagofacil_transaction_id=tx.pagofacil_transaction_id,
            fecha_pago=None,
            mensaje="El pago aún se encuentra pendiente de escaneo/confirmación"
        )

    except Exception as e:
        logger.warning(f"Error consultando transacción a PagoFácil: {e}")
        return ConsultarTransaccionResponse(
            success=True,
            payment_number=tx.payment_number,
            estado=tx.estado,
            pagado=(tx.estado == "completado"),
            monto=float(tx.monto),
            moneda=tx.moneda,
            pagofacil_transaction_id=tx.pagofacil_transaction_id,
            fecha_pago=None,
            mensaje=f"Estado en sistema: {tx.estado}"
        )
