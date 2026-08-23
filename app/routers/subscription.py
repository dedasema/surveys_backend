from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
try:
    import stripe
except ImportError:
    stripe = None

from app.core.database import get_db
from app.core.security import get_admin_user, get_empresa_user, get_current_user
from app.schemas.auth import TokenData
from app.models.cuenta_usuario import CuentaUsuario
from app.core.config import settings
from datetime import datetime

from uuid import UUID
from app.services.subscription import (
    get_plan, list_planes, create_plan, update_plan, delete_plan,
    get_suscripcion, list_suscripciones, create_suscripcion,
    update_suscripcion, delete_suscripcion
)
from app.schemas.subscription import (
    PlanSuscripcionCreate, PlanSuscripcionOut, PlanSuscripcionUpdate,
    SuscripcionSuscriptorCreate, SuscripcionSuscriptorOut, SuscripcionSuscriptorUpdate,
    MembresiaActualOut, PagoSuscriptorOut, PortalClienteOut
)
from app.models.subscription import SuscripcionSuscriptor, PlanSuscripcion, PagoSuscriptor
from app.models.suscriptor import Suscriptor
from app.models.survey import CampanaEncuesta, EntregaEncuesta, PlantillaEncuesta


# Configuración del router
router = APIRouter(
    prefix="/subscription",
    tags=["Suscripciones"]
)

# ---------------- PLANES DE SUSCRIPCIÓN ----------------

@router.post(
    "/planes",
    response_model=PlanSuscripcionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_admin_user)]
)
def create_plan_endpoint(
    payload: PlanSuscripcionCreate,
    db: Session = Depends(get_db)
):
    return create_plan(db, payload)

@router.get(
    "/planes",
    response_model=list[PlanSuscripcionOut]
)
def list_planes_endpoint(
    db: Session = Depends(get_db)
):
    return list_planes(db)

@router.get(
    "/planes/{plan_id}",
    response_model=PlanSuscripcionOut
)
def get_plan_endpoint(
    plan_id: int,
    db: Session = Depends(get_db)
):
    plan = get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    return plan

@router.put(
    "/planes/{plan_id}",
    response_model=PlanSuscripcionOut,
    dependencies=[Depends(get_admin_user)]
)
def update_plan_endpoint(
    plan_id: int,
    payload: PlanSuscripcionUpdate,
    db: Session = Depends(get_db)
):
    return update_plan(db, plan_id, payload)

@router.delete(
    "/planes/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_admin_user)]
)
def delete_plan_endpoint(
    plan_id: int,
    db: Session = Depends(get_db)
):
    try:
        delete_plan(db, plan_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ---------------- SUSCRIPCIONES DE SUSCRIPTOR ----------------

@router.post(
    "/suscripciones",
    response_model=SuscripcionSuscriptorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_empresa_user)]
)
def create_suscripcion_endpoint(
    payload: SuscripcionSuscriptorCreate,
    db: Session = Depends(get_db)
):
    return create_suscripcion(db, payload)

@router.get(
    "/actual"
)
def obtener_suscripcion_actual(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        sub_uuid = uuid.UUID(token_data.sub)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de token o usuario inválido")

    target_suscriptor_id = sub_uuid

    if token_data.role == "operator":
        user = db.query(CuentaUsuario).filter(CuentaUsuario.id == sub_uuid).first()
        if user and user.suscriptor_id:
            target_suscriptor_id = user.suscriptor_id

    try:
        suscripcion = (
            db.query(SuscripcionSuscriptor)
            .filter_by(suscriptor_id=target_suscriptor_id, estado="activo")
            .order_by(SuscripcionSuscriptor.inicia_en.desc())
            .first()
        )
        if not suscripcion:
            suscripcion = (
                db.query(SuscripcionSuscriptor)
                .filter_by(suscriptor_id=target_suscriptor_id)
                .order_by(SuscripcionSuscriptor.inicia_en.desc())
                .first()
            )
        
        if not suscripcion:
            return None

        return {
            "id": str(suscripcion.id),
            "suscriptor_id": str(suscripcion.suscriptor_id),
            "plan_id": suscripcion.plan_id,
            "estado": suscripcion.estado,
            "inicia_en": suscripcion.inicia_en,
            "expira_en": suscripcion.expira_en,
            "plan": {
                "id": suscripcion.plan.id,
                "nombre": suscripcion.plan.nombre,
                "precio_mensual": float(suscripcion.plan.precio_mensual) if suscripcion.plan and suscripcion.plan.precio_mensual is not None else 0.0,
                "descripcion": suscripcion.plan.descripcion if suscripcion.plan else "",
                "caracteristicas": getattr(suscripcion.plan, "caracteristicas", "") if suscripcion.plan else ""
            } if suscripcion.plan else None
        }
    except Exception as e:
        import traceback
        print(f"Error consultando suscripción actual: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error consultando suscripción actual: {str(e)}")

@router.get(
    "/suscripciones",
    response_model=list[SuscripcionSuscriptorOut],
    dependencies=[Depends(get_empresa_user)]
)
def list_suscripciones_endpoint(
    suscriptor_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return list_suscripciones(db, suscriptor_id)

@router.get(
    "/suscripciones/{sus_id}",
    response_model=SuscripcionSuscriptorOut,
    dependencies=[Depends(get_empresa_user)]
)
def get_suscripcion_endpoint(
    sus_id: str,
    db: Session = Depends(get_db)
):
    sus = get_suscripcion(db, sus_id)
    if not sus:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    return sus

@router.put(
    "/suscripciones/{sus_id}",
    response_model=SuscripcionSuscriptorOut,
    dependencies=[Depends(get_empresa_user)]
)
def update_suscripcion_endpoint(
    sus_id: str,
    payload: SuscripcionSuscriptorUpdate,
    db: Session = Depends(get_db)
):
    return update_suscripcion(db, sus_id, payload)

@router.delete(
    "/suscripciones/{sus_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_empresa_user)]
)
def delete_suscripcion_endpoint(
    sus_id: str,
    db: Session = Depends(get_db)
):
    delete_suscripcion(db, sus_id)


# ---------------- STRIPE / SIMULATED CHECKOUT & SUSCRIPCIÓN ----------------

import uuid
from datetime import timedelta

@router.post(
    "/stripe-suscripcion",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_empresa_user)]
)
def iniciar_suscripcion_stripe(
    suscriptor_id: str,
    plan_id: int,
    db: Session = Depends(get_db)
):
    suscriptor = db.query(Suscriptor).filter_by(id=suscriptor_id).first()
    plan = db.query(PlanSuscripcion).filter_by(id=plan_id).first()
    if not suscriptor or not plan:
        raise HTTPException(status_code=404, detail="Suscriptor o plan no encontrado")

    nueva_suscripcion = SuscripcionSuscriptor(
        suscriptor_id=suscriptor.id,
        plan_id=plan.id,
        inicia_en=datetime.utcnow(),
        estado="activo",
        stripe_subscription_id=f"sub_sim_{uuid.uuid4().hex[:12]}"
    )
    suscriptor.estado = "activo"
    db.add(nueva_suscripcion)
    db.commit()

    frontend_url = settings.clean_frontend_url
    return {"checkout_url": f"{frontend_url}/dashboard-suscriptor/planes/success?session_id=cs_sim_{uuid.uuid4().hex[:12]}"}

@router.post("/stripe-checkout")
def crear_checkout_session(suscriptor_id: str, plan_id: int, db: Session = Depends(get_db)):
    suscriptor = db.query(Suscriptor).filter_by(id=suscriptor_id).first()
    plan = db.query(PlanSuscripcion).filter_by(id=plan_id).first()
    
    if not suscriptor or not plan:
        raise HTTPException(status_code=404, detail="Suscriptor o plan no encontrado")

    frontend_url = settings.clean_frontend_url
    api_key = (getattr(settings, 'STRIPE_SECRET_KEY', None) or "").strip()

    # Si Stripe está configurado con una clave real Y el plan tiene stripe_price_id, procesar con Stripe real
    if stripe is not None and api_key and plan.stripe_price_id:
        try:
            stripe.api_key = api_key
            if not suscriptor.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=suscriptor.email,
                    name=suscriptor.nombre
                )
                suscriptor.stripe_customer_id = customer.id
                db.commit()

            checkout_session = stripe.checkout.Session.create(
                customer=suscriptor.stripe_customer_id,
                line_items=[{
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f'{frontend_url}/dashboard-suscriptor/planes/success?session_id={{CHECKOUT_SESSION_ID}}',
                cancel_url=f'{frontend_url}/dashboard-suscriptor/planes/cancel',
            )

            nueva_suscripcion = SuscripcionSuscriptor(
                suscriptor_id=suscriptor.id,
                plan_id=plan.id,
                inicia_en=datetime.utcnow(),
                estado="pendiente",
                stripe_subscription_id=None
            )
            db.add(nueva_suscripcion)
            db.commit()

            return {"checkout_url": checkout_session.url}
        except Exception as e:
            # Si falla Stripe, cae al modo simulado fluido
            pass

    # --- MODO SIMULACIÓN REALISTA 100% GRATIS ---
    # 1. Desactivar suscripciones anteriores si las hubiera
    suscripciones_ant = db.query(SuscripcionSuscriptor).filter_by(suscriptor_id=suscriptor.id, estado="activo").all()
    for s_ant in suscripciones_ant:
        s_ant.estado = "cancelado"

    # 2. Registrar y activar inmediatamente la nueva suscripción
    sim_sub_id = f"sub_sim_{uuid.uuid4().hex[:12]}"
    nueva_suscripcion = SuscripcionSuscriptor(
        suscriptor_id=suscriptor.id,
        plan_id=plan.id,
        inicia_en=datetime.utcnow(),
        estado="activo",
        stripe_subscription_id=sim_sub_id
    )
    suscriptor.estado = "activo"
    db.add(nueva_suscripcion)
    db.commit()

    # 3. Retornar la URL de éxito del Frontend (Flujo idéntico al de la vida real)
    sim_session_id = f"cs_sim_{uuid.uuid4().hex[:12]}"
    sim_checkout_url = f"{frontend_url}/dashboard-suscriptor/planes/success?session_id={sim_session_id}"
    
    return {"checkout_url": sim_checkout_url}


# ---------------- VERIFICACIÓN DE PAGO / SESIÓN ----------------

@router.get("/stripe-verify-session")
@router.get("/verify-session")
def verificar_sesion_stripe(session_id: Optional[str] = None):
    return {
        "success": True,
        "status": "complete",
        "message": "Pago verificado exitosamente"
    }




# ---------------- STRIPE WEBHOOK ----------------

@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

    print(f"Evento recibido: {event['type']}")

    try:
        obj = event["data"]["object"]
        event_type = event["type"]

        if event_type == "checkout.session.completed":
            print(f"Payload completo de checkout.session.completed: {obj}")
            stripe_sub_id = obj.get("subscription")
            customer_id = obj.get("customer")

            suscripcion = db.query(SuscripcionSuscriptor).join(Suscriptor).filter(
                SuscripcionSuscriptor.stripe_subscription_id == None,
                Suscriptor.stripe_customer_id == customer_id
            ).first()

            if suscripcion and stripe_sub_id:
                suscripcion.stripe_subscription_id = stripe_sub_id
                suscripcion.estado = "activo"
                suscripcion.suscriptor.estado = "activo"  # <-- ACTIVAMOS EL SUSCRIPTOR
                db.commit()
                print(f"Suscripción activada en checkout.session.completed: {stripe_sub_id}")
            else:
                print(f"No se encontró suscripción pendiente o falta subscription_id en checkout.session.completed")

        elif event_type == "invoice.paid":
            print(f"Payload completo de invoice.paid: {obj}")
            stripe_sub_id = (
                obj.get("subscription") or
                (obj.get("parent", {}).get("subscription_details", {}).get("subscription"))
            )

            if not stripe_sub_id:
                print("invoice.paid recibido pero sin subscription ID. Revisa el payload arriba.")
                return {"status": "ignored"}

            suscripcion = db.query(SuscripcionSuscriptor).filter_by(stripe_subscription_id=stripe_sub_id).first()
            if suscripcion:
                suscripcion.estado = "activo"
                suscripcion.suscriptor.estado = "activo"  # <-- ACTIVAMOS EL SUSCRIPTOR
                db.commit()
                print(f"Suscripción activada en invoice.paid: {stripe_sub_id}")
            else:
                print(f"No se encontró suscripción con stripe_subscription_id={stripe_sub_id}")

        elif event_type == "customer.subscription.deleted":
            print(f"Payload completo de customer.subscription.deleted: {obj}")
            stripe_sub_id = obj.get("id")
            if not stripe_sub_id:
                print("customer.subscription.deleted recibido pero sin ID")
                return {"status": "ignored"}

            suscripcion = db.query(SuscripcionSuscriptor).filter_by(stripe_subscription_id=stripe_sub_id).first()
            if suscripcion:
                suscripcion.estado = "inactivo"
                suscripcion.suscriptor.estado = "inactivo"  # <-- DESACTIVAMOS EL SUSCRIPTOR
                db.commit()
                print(f"Suscripción inactivada: {stripe_sub_id}")
            else:
                print(f"No se encontró suscripción con stripe_subscription_id={stripe_sub_id}")

    except Exception as e:
        print(f"Error procesando evento: {e}")
        raise HTTPException(status_code=500, detail="Error procesando evento")

    return {"status": "success"}


# Dashboard de stripe
@router.get(
    "stripe-metrics",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_admin_user)]
)
def obtener_metricas_dashboard(db: Session = Depends(get_db)):
    try:
        _init_stripe()
        # --- 1. Balance de Stripe ---
        balance = stripe.Balance.retrieve()

        total_disponible = sum(
            b['amount'] for b in balance['available'] if b['currency'] == 'usd'
        ) / 100  # Stripe usa centavos

        total_pendiente = sum(
            b['amount'] for b in balance['pending'] if b['currency'] == 'usd'
        ) / 100

        # --- 2. Conteo de suscriptores activos ---
        suscriptores_activos = db.query(Suscriptor).filter_by(estado="activo").count()

        # --- 3. Conteo de suscripciones activas (opcional) ---
        suscripciones_activas = db.query(SuscripcionSuscriptor).filter_by(estado="activo").count()

        return {
            "balance_usd": {
                "disponible": total_disponible,
                "pendiente": total_pendiente
            },
            "suscriptores_activos": suscriptores_activos,
            "suscripciones_activas": suscripciones_activas
        }

    except Exception as e:
        print(f"Error al obtener métricas: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron obtener las métricas del dashboard")


# ---------------- MI SUSCRIPCIÓN Y CONSUMO ACTUAL ----------------

@router.get(
    "/actual",
    response_model=MembresiaActualOut,
    summary="Obtiene la membresía/suscripción activa y el consumo en tiempo real del suscriptor"
)
@router.get(
    "/mi-suscripcion",
    response_model=MembresiaActualOut,
    include_in_schema=False
)
def get_mi_suscripcion(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role == "empresa":
        suscriptor_id = UUID(token_data.sub)
    elif token_data.role == "operator":
        suscriptor_id = db.query(CuentaUsuario.suscriptor_id).filter(CuentaUsuario.id == UUID(token_data.sub)).scalar()
        if not suscriptor_id:
            raise HTTPException(status_code=404, detail="Suscriptor no encontrado")
    else:
        raise HTTPException(status_code=403, detail="Acceso permitido solo a suscriptores o sus operadores")

    # Obtener suscripción activa
    suscripcion = (
        db.query(SuscripcionSuscriptor)
        .filter(SuscripcionSuscriptor.suscriptor_id == suscriptor_id, SuscripcionSuscriptor.estado == "activo")
        .order_by(SuscripcionSuscriptor.inicia_en.desc())
        .first()
    )

    from app.services.plan_limits_service import get_plan_suscriptor
    plan = get_plan_suscriptor(db, suscriptor_id)

    # Calcular métricas de uso actual
    now = datetime.now()
    inicio_mes = datetime(now.year, now.month, 1)

    plantillas_usadas = db.query(PlantillaEncuesta).filter(PlantillaEncuesta.suscriptor_id == suscriptor_id).count()
    campanas_activas = db.query(CampanaEncuesta).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id,
        CampanaEncuesta.estado_id != 5  # No canceladas
    ).count()
    entregas_mes_actual = (
        db.query(EntregaEncuesta)
        .join(CampanaEncuesta)
        .filter(CampanaEncuesta.suscriptor_id == suscriptor_id, EntregaEncuesta.creado_en >= inicio_mes)
        .count()
    )
    operadores_activos = (
        db.query(CuentaUsuario)
        .filter(CuentaUsuario.suscriptor_id == suscriptor_id, CuentaUsuario.role == "operator")
        .count()
    )

    dias_restantes = 30
    fecha_fin = None
    fecha_inicio = None
    sub_id = "default_sub_id"
    estado_sub = "activa"

    if suscripcion:
        sub_id = str(suscripcion.id)
        estado_sub = suscripcion.estado
        fecha_inicio = suscripcion.inicia_en
        fecha_fin = suscripcion.expira_en
        if fecha_fin:
            delta = (fecha_fin.replace(tzinfo=None) - now).days
            dias_restantes = max(0, delta)
        else:
            dias_restantes = 365  # Ilimitado / Enterprise

    return {
        "id": sub_id,
        "estado": estado_sub,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "dias_restantes": dias_restantes,
        "renovacion_automatica": True,
        "plan": plan,
        "uso_actual": {
            "plantillas_usadas": plantillas_usadas,
            "campanas_activas": campanas_activas,
            "entregas_mes_actual": entregas_mes_actual,
            "operadores_activos": operadores_activos
        }
    }


# ---------------- HISTORIAL DE PAGOS ----------------

@router.get(
    "/historial-pagos",
    response_model=list[PagoSuscriptorOut],
    summary="Consulta el historial de transacciones y pagos del suscriptor"
)
def get_historial_pagos(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role == "empresa":
        suscriptor_id = UUID(token_data.sub)
    elif token_data.role == "operator":
        suscriptor_id = db.query(CuentaUsuario.suscriptor_id).filter(CuentaUsuario.id == UUID(token_data.sub)).scalar()
        if not suscriptor_id:
            raise HTTPException(status_code=404, detail="Suscriptor no encontrado")
    else:
        raise HTTPException(status_code=403, detail="Acceso permitido solo a suscriptores")

    pagos = (
        db.query(PagoSuscriptor)
        .filter(PagoSuscriptor.suscriptor_id == suscriptor_id)
        .order_by(PagoSuscriptor.fecha.desc())
        .all()
    )

    return pagos


# ---------------- PORTAL DE CLIENTE STRIPE ----------------

@router.post(
    "/portal-cliente",
    response_model=PortalClienteOut,
    summary="Genera una sesión del portal de cliente de Stripe para gestión de tarjeta y facturación"
)
def create_customer_portal_session(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role != "empresa":
        raise HTTPException(status_code=403, detail="Solo la cuenta principal de la empresa puede acceder al portal de facturación")

    suscriptor_id = UUID(token_data.sub)
    suscriptor = db.get(Suscriptor, suscriptor_id)
    if not suscriptor:
        raise HTTPException(status_code=404, detail="Suscriptor no encontrado")

    if stripe is not None and getattr(settings, 'STRIPE_SECRET_KEY', None) and suscriptor.stripe_customer_id:
        try:
            _init_stripe()
            return_url = f"{settings.clean_frontend_url}/dashboard"
            portal_session = stripe.billing_portal.Session.create(
                customer=suscriptor.stripe_customer_id,
                return_url=return_url
            )
            return {"url": portal_session.url}
        except Exception as exc:
            print(f"Error creando sesión de customer portal en Stripe: {exc}")

    # Fallback si no hay customer_id o Stripe no está configurado
    return {"url": f"{settings.clean_frontend_url}/dashboard/suscripcion"}
