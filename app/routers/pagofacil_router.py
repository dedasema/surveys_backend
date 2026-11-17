# app/routers/pagofacil_router.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.models.cuenta_usuario import CuentaUsuario
from app.models.suscriptor import Suscriptor
from app.models.pagofacil import PagoFacilTransaccion
from app.schemas.pagofacil import (
    GenerarQRPayload,
    GenerarQRResponse,
    ConsultarTransaccionResponse,
    PagoFacilCallbackPayload,
    PagoFacilCallbackResponse,
    MetodosHabilitadosResponse,
    PagoFacilTransaccionOut,
    TipoCambioResponse
)
from app.services.tipo_cambio_service import obtener_tipo_cambio_oficial
from app.services.pagofacil_service import (
    pagofacil_client,
    crear_orden_qr,
    consultar_estado_transaccion,
    procesar_callback_pagofacil
)

router = APIRouter(
    prefix="/pagofacil",
    tags=["PagoFácil QR"]
)

subscription_pagofacil_router = APIRouter(
    prefix="/subscription/pagofacil",
    tags=["PagoFácil QR"]
)

def _resolver_suscriptor_id(db: Session, token_data: TokenData) -> UUID:
    if token_data.role == "empresa":
        return UUID(token_data.sub)
    elif token_data.role in ["operator", "empresa_operador"]:
        cuenta = db.query(CuentaUsuario).filter(CuentaUsuario.id == UUID(token_data.sub)).first()
        if not cuenta:
            raise HTTPException(status_code=404, detail="Cuenta de usuario no encontrada")
        return cuenta.suscriptor_id
    elif token_data.role == "admin":
        primer_sus = db.query(Suscriptor).first()
        if not primer_sus:
            raise HTTPException(status_code=404, detail="No existen empresas registradas")
        return primer_sus.id
    else:
        raise HTTPException(status_code=403, detail="No tienes permisos para realizar pagos")

# ─────────────────── Endpoints ─────────────────── #

@router.get("/tipo-cambio", response_model=TipoCambioResponse)
@subscription_pagofacil_router.get("/tipo-cambio", response_model=TipoCambioResponse)
async def get_tipo_cambio_del_dia(
    refrescar: bool = Query(False, description="Forzar refresco desde la API oficial del BCB")
):
    """
    Obtiene el tipo de cambio oficial del día (USD a BOB).
    Utiliza como fuente el Banco Central de Bolivia (BCB) con fallback automático a 7.00.
    """
    valor, es_fallback, meta = await obtener_tipo_cambio_oficial(forzar_refresco=refrescar)
    return {
        "valor": valor,
        "fuente": meta.get("fuente", "Banco Central de Bolivia (bcb.gob.bo)"),
        "moneda": "USD/BOB",
        "fecha": meta.get("fecha"),
        "es_fallback": es_fallback
    }

@router.get("/metodos", response_model=MetodosHabilitadosResponse)
@subscription_pagofacil_router.get("/metodos", response_model=MetodosHabilitadosResponse)
async def get_metodos_habilitados():
    """
    Lista los métodos de pago QR habilitados para el comercio desde la API de PagoFácil.
    """
    try:
        metodos = await pagofacil_client.list_enabled_services()
        return {
            "error": 0,
            "status": 2006,
            "message": "Lista de servicios QR habilitados recuperada exitosamente.",
            "values": metodos
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando métodos de PagoFácil: {str(e)}")

@router.post("/generar-qr", response_model=GenerarQRResponse, status_code=status.HTTP_201_CREATED)
@subscription_pagofacil_router.post("/generar-qr", response_model=GenerarQRResponse, status_code=status.HTTP_201_CREATED)
async def endpoint_generar_qr(
    payload: GenerarQRPayload,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Crea una orden de pago en PagoFácil y genera la imagen del código QR (base64)
    para la suscripción a un plan.
    """
    suscriptor_id = _resolver_suscriptor_id(db, token_data)
    try:
        resultado = await crear_orden_qr(db, suscriptor_id, payload)
        return resultado
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/consultar/{payment_number}", response_model=ConsultarTransaccionResponse)
@router.get("/estado/{payment_number}", response_model=ConsultarTransaccionResponse)
@subscription_pagofacil_router.get("/consultar/{payment_number}", response_model=ConsultarTransaccionResponse)
@subscription_pagofacil_router.get("/estado/{payment_number}", response_model=ConsultarTransaccionResponse)
async def endpoint_consultar_estado(
    payment_number: str,
    db: Session = Depends(get_db)
):
    """
    Verifica el estado actual de una transacción por su payment_number (PedidoID).
    Permite polling continuo desde el Frontend mientras el usuario escanea el QR.
    """
    try:
        resultado = await consultar_estado_transaccion(db, payment_number)
        return resultado
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/callback", response_model=PagoFacilCallbackResponse, status_code=status.HTTP_200_OK)
@subscription_pagofacil_router.post("/callback", response_model=PagoFacilCallbackResponse, status_code=status.HTTP_200_OK)
async def endpoint_callback(
    payload: PagoFacilCallbackPayload,
    db: Session = Depends(get_db)
):
    """
    URL Callback pública oficial requerida por PagoFácil.
    Recibe la notificación automática POST tras el pago del cliente y activa la suscripción en tiempo real.
    """
    try:
        respuesta = procesar_callback_pagofacil(db, payload)
        return respuesta
    except Exception as e:
        # En caso de error interno, responder con estructura JSON esperada
        return PagoFacilCallbackResponse(
            error=1,
            status=0,
            message=f"Error procesando callback: {str(e)}",
            values=False
        )

@router.get("/transacciones", response_model=List[PagoFacilTransaccionOut])
@subscription_pagofacil_router.get("/transacciones", response_model=List[PagoFacilTransaccionOut])
def listar_transacciones_suscriptor(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lista el historial de transacciones PagoFácil generadas para la empresa autenticada.
    """
    suscriptor_id = _resolver_suscriptor_id(db, token_data)
    transacciones = (
        db.query(PagoFacilTransaccion)
        .filter_by(suscriptor_id=suscriptor_id)
        .order_by(PagoFacilTransaccion.creado_en.desc())
        .limit(50)
        .all()
    )
    return [
        PagoFacilTransaccionOut(
            id=str(t.id),
            payment_number=t.payment_number,
            plan_id=t.plan_id,
            monto=float(t.monto),
            monto_qr=float(t.monto_qr) if t.monto_qr is not None else None,
            tipo_cambio=float(t.tipo_cambio) if t.tipo_cambio is not None else None,
            moneda=t.moneda,
            estado=t.estado,
            pagofacil_transaction_id=t.pagofacil_transaction_id,
            qr_base64=t.qr_base64,
            checkout_url=t.checkout_url,
            creado_en=t.creado_en.isoformat() if t.creado_en else None
        )
        for t in transacciones
    ]
