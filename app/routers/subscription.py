from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
try:
    import stripe
except ImportError:
    stripe = None

from app.core.database import get_db
from app.core.security import get_admin_user, get_empresa_user
from app.core.config import settings
from datetime import datetime

from app.services.subscription import (
    get_plan, list_planes, create_plan, update_plan, delete_plan,
    get_suscripcion, list_suscripciones, create_suscripcion,
    update_suscripcion, delete_suscripcion
)
from app.schemas.subscription import (
    PlanSuscripcionCreate, PlanSuscripcionOut, PlanSuscripcionUpdate,
    SuscripcionSuscriptorCreate, SuscripcionSuscriptorOut, SuscripcionSuscriptorUpdate
)
from app.models.subscription import SuscripcionSuscriptor
from app.models.suscriptor import Suscriptor
from app.models.subscription import PlanSuscripcion


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
    delete_plan(db, plan_id)


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
