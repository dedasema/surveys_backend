import logging
from datetime import datetime
from uuid import UUID
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.models.survey import CampanaEncuesta, EntregaEncuesta, PlantillaEncuesta
from app.models.cuenta_usuario import CuentaUsuario

logger = logging.getLogger(__name__)


def get_plan_suscriptor(db: Session, suscriptor_id: UUID) -> PlanSuscripcion:
    """
    Obtiene el plan activo del suscriptor o cae al plan Gratuito por defecto.
    """
    suscripcion = (
        db.query(SuscripcionSuscriptor)
        .filter(
            SuscripcionSuscriptor.suscriptor_id == suscriptor_id,
            SuscripcionSuscriptor.estado == "activo"
        )
        .order_by(SuscripcionSuscriptor.inicia_en.desc())
        .first()
    )
    if suscripcion and suscripcion.plan:
        return suscripcion.plan

    # Fallback: Buscar plan Gratuito por defecto
    plan_gratuito = db.query(PlanSuscripcion).filter(PlanSuscripcion.nombre.ilike("%Gratuito%")).first()
    if plan_gratuito:
        return plan_gratuito

    # Si no existe en BD, instanciar un objeto por defecto
    return PlanSuscripcion(
        id=0,
        nombre="Gratuito Default",
        precio_mensual=0.0,
        max_plantillas=3,
        max_campanas=2,
        max_entregas=100,
        max_operadores=1,
        permite_email=True,
        permite_audio_voz=True,
        permite_papel=True,
        permite_ia_analisis=False,
        permite_exportacion=True,
        activo=True
    )


def validate_plantillas_limit(db: Session, suscriptor_id: UUID) -> None:
    """
    Valida si el suscriptor ha alcanzado el límite de plantillas para su plan.
    """
    plan = get_plan_suscriptor(db, suscriptor_id)
    if plan.max_plantillas == -1 or plan.max_plantillas == 0:
        return  # Ilimitado

    current_count = db.query(PlantillaEncuesta).filter(PlantillaEncuesta.suscriptor_id == suscriptor_id).count()
    if current_count >= plan.max_plantillas:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Has alcanzado el límite de plantillas para tu plan."
        )


def validate_campanas_limit(db: Session, suscriptor_id: UUID) -> None:
    """
    Valida si el suscriptor ha alcanzado el límite de campañas para su plan.
    """
    plan = get_plan_suscriptor(db, suscriptor_id)
    if plan.max_campanas == -1:
        return  # Ilimitado

    current_count = db.query(CampanaEncuesta).filter(CampanaEncuesta.suscriptor_id == suscriptor_id).count()
    if current_count >= plan.max_campanas:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Has alcanzado el límite de campañas para tu plan."
        )


def validate_operadores_limit(db: Session, suscriptor_id: UUID) -> None:
    """
    Valida si el suscriptor ha alcanzado el número máximo de operadores permitidos.
    """
    plan = get_plan_suscriptor(db, suscriptor_id)
    if plan.max_operadores == -1:
        return  # Ilimitado

    from app.models.catalogos import Rol
    current_count = (
        db.query(CuentaUsuario)
        .join(CuentaUsuario.rol)
        .filter(CuentaUsuario.suscriptor_id == suscriptor_id, Rol.nombre == "operator")
        .count()
    )
    if current_count >= plan.max_operadores:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Has alcanzado el límite de operadores para tu plan."
        )


def validate_entregas_limit(db: Session, suscriptor_id: UUID, nuevas_entregas: int = 1) -> None:
    """
    Valida la cuota mensual de entregas del suscriptor.
    """
    plan = get_plan_suscriptor(db, suscriptor_id)
    if plan.max_entregas == -1:
        return  # Ilimitado

    now = datetime.now()
    inicio_mes = datetime(now.year, now.month, 1)

    from sqlalchemy.sql import func
    # Entregas creadas este mes
    current_count = (
        db.query(EntregaEncuesta)
        .join(CampanaEncuesta)
        .filter(
            CampanaEncuesta.suscriptor_id == suscriptor_id,
            func.coalesce(EntregaEncuesta.enviado_en, EntregaEncuesta.respondido_en, CampanaEncuesta.creado_en) >= inicio_mes
        )
        .count()
    )

    if (current_count + nuevas_entregas) > plan.max_entregas:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"La cantidad de entregas supera la cuota mensual de tu plan ({plan.max_entregas} entregas/mes)."
        )


def validate_canal_permission(db: Session, suscriptor_id: UUID, canal_id: int) -> None:
    """
    Valida si el plan del suscriptor incluye permisos para utilizar un canal específico.
    - Canal 1 (Email): permite_email
    - Canal 4 (Papel/OCR): permite_papel
    - Canal 5 (Audio/Voz): permite_audio_voz
    """
    plan = get_plan_suscriptor(db, suscriptor_id)

    if canal_id == 1 and not plan.permite_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu plan actual no incluye encuestas por Email."
        )

    if canal_id == 4 and not plan.permite_papel:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu plan actual no incluye encuestas en Papel con OCR IA. Actualiza tu suscripción."
        )

    if canal_id == 5 and not plan.permite_audio_voz:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu plan actual no incluye encuestas asistidas por voz con IA. Actualiza tu suscripción."
        )
