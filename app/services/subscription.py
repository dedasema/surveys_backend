try:
    import stripe
except ImportError:
    stripe = None
import logging
from sqlalchemy.orm import Session
from typing import List, Optional

logger = logging.getLogger(__name__)

from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.schemas.subscription import (
    PlanSuscripcionCreate, PlanSuscripcionUpdate,
    SuscripcionSuscriptorCreate, SuscripcionSuscriptorUpdate
)
from app.core.config import settings

if stripe is not None:
    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)

# ---------------- PlanSuscripcion ----------------

def get_plan(db: Session, plan_id: int) -> PlanSuscripcion | None:
    return db.get(PlanSuscripcion, plan_id)

def list_planes(db: Session) -> List[PlanSuscripcion]:
    return db.query(PlanSuscripcion).filter(PlanSuscripcion.activo == True).all()

def create_plan(db: Session, payload: PlanSuscripcionCreate) -> PlanSuscripcion:
    stripe_price_id = None
    if stripe is not None and getattr(settings, 'STRIPE_SECRET_KEY', None):
        try:
            product = stripe.Product.create(name=payload.nombre)
            price = stripe.Price.create(
                unit_amount=int(payload.precio_mensual * 100),
                currency="usd",
                recurring={"interval": "month"},
                product=product.id
            )
            stripe_price_id = price.id
        except Exception as exc:
            logger.warning("No se pudo crear producto/precio en Stripe: %s", exc)

    plan = PlanSuscripcion(
        nombre=payload.nombre,
        precio_mensual=payload.precio_mensual,
        descripcion=payload.descripcion,
        max_plantillas=payload.max_plantillas,
        max_campanas=payload.max_campanas,
        max_entregas=payload.max_entregas,
        max_operadores=payload.max_operadores,
        permite_email=payload.permite_email,
        permite_audio_voz=payload.permite_audio_voz,
        permite_papel=payload.permite_papel,
        permite_ia_analisis=payload.permite_ia_analisis,
        permite_exportacion=payload.permite_exportacion,
        caracteristicas=payload.caracteristicas,
        activo=payload.activo,
        stripe_price_id=stripe_price_id or payload.stripe_price_id
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

def update_plan(db: Session, plan_id: int, payload: PlanSuscripcionUpdate) -> PlanSuscripcion:
    plan = get_plan(db, plan_id)
    if not plan:
        raise Exception("Plan no encontrado")

    if stripe is not None and getattr(settings, 'STRIPE_SECRET_KEY', None) and plan.stripe_price_id:
        try:
            price = stripe.Price.retrieve(plan.stripe_price_id)
            product_id = price.product
            if payload.nombre:
                stripe.Product.modify(product_id, name=payload.nombre)
            if payload.precio_mensual and payload.precio_mensual != plan.precio_mensual:
                new_price = stripe.Price.create(
                    unit_amount=int(payload.precio_mensual * 100),
                    currency="usd",
                    recurring={"interval": "month"},
                    product=product_id
                )
                plan.stripe_price_id = new_price.id
        except Exception as exc:
            logger.warning("No se pudo actualizar producto/precio en Stripe: %s", exc)

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            setattr(plan, key, value)

    db.commit()
    db.refresh(plan)
    return plan

def delete_plan(db: Session, plan_id: int) -> None:
    plan = get_plan(db, plan_id)
    if not plan:
        raise Exception("Plan no encontrado")

    # Validar que no tenga suscriptores activos
    suscritos = db.query(SuscripcionSuscriptor).filter(
        SuscripcionSuscriptor.plan_id == plan_id,
        SuscripcionSuscriptor.estado == "activo"
    ).count()
    if suscritos > 0:
        raise Exception(f"No se puede eliminar el plan {plan.nombre} porque tiene {suscritos} suscriptores activos.")

    if stripe is not None and getattr(settings, 'STRIPE_SECRET_KEY', None) and plan.stripe_price_id:
        try:
            price = stripe.Price.retrieve(plan.stripe_price_id)
            product_id = price.product
            stripe.Product.modify(product_id, active=False)
            stripe.Price.modify(plan.stripe_price_id, active=False)
        except Exception as exc:
            logger.warning("No se pudo desactivar en Stripe: %s", exc)

    # Borrado lógico desactivándolo
    plan.activo = False
    db.commit()

# ---------------- SuscripcionSuscriptor (sin cambios) ----------------

def get_suscripcion(db: Session, sus_id: str) -> SuscripcionSuscriptor | None:
    return db.get(SuscripcionSuscriptor, sus_id)

def list_suscripciones(db: Session, suscriptor_id: Optional[str] = None) -> List[SuscripcionSuscriptor]:
    q = db.query(SuscripcionSuscriptor)
    if suscriptor_id:
        q = q.filter_by(suscriptor_id=suscriptor_id)
    return q.all()

def create_suscripcion(db: Session, payload: SuscripcionSuscriptorCreate) -> SuscripcionSuscriptor:
    sus = SuscripcionSuscriptor(**payload.model_dump())
    db.add(sus)
    db.commit()
    db.refresh(sus)
    return sus

def update_suscripcion(db: Session, sus_id: str, payload: SuscripcionSuscriptorUpdate) -> SuscripcionSuscriptor:
    sus = get_suscripcion(db, sus_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sus, k, v)
    db.commit()
    db.refresh(sus)
    return sus

def delete_suscripcion(db: Session, sus_id: str) -> None:
    sus = get_suscripcion(db, sus_id)
    if not sus:
        raise Exception("Suscripción no encontrada")

    # 🔑 Cancelar la suscripción en Stripe si existe
    if sus.stripe_subscription_id:
        try:
            response = stripe.Subscription.delete(sus.stripe_subscription_id)
            if response["status"] != "canceled":
                print(f"⚠️ Stripe no canceló la suscripción: {response}")
                raise Exception("No se pudo cancelar la suscripción en Stripe")
            else:
                print(f"✅ Stripe canceló la suscripción: {sus.stripe_subscription_id}")
        except Exception as e:
            print(f"❌ Error al cancelar en Stripe: {e}")
            raise Exception(f"Error al cancelar en Stripe: {e}")

    # Eliminar en base de datos solo si se canceló exitosamente
    db.delete(sus)
    db.commit()
    print(f"✅ Suscripción eliminada en base de datos: {sus.id}")
