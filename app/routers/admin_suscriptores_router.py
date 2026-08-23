from typing import List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_admin_user
from app.models.suscriptor import Suscriptor
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor, PagoSuscriptor
from app.models.cuenta_usuario import CuentaUsuario
from app.models.survey import CampanaEncuesta, EntregaEncuesta, PlantillaEncuesta
from app.services.plan_limits_service import get_plan_suscriptor
from app.schemas.subscription import PagoSuscriptorOut, PlanSuscripcionOut
from app.schemas.admin_suscriptores_schema import (
    SuscriptorListOut,
    SuscriptorDetail360Out,
    SuscriptorEstadoUpdate,
    SuscriptorAsignarPlan,
    OperadorOut,
    ResumenUsoAdminOut
)

router = APIRouter(
    prefix="/admin/suscriptores",
    tags=["Admin - Suscriptores"],
    dependencies=[Depends(get_admin_user)]
)


def _build_resumen_uso(db: Session, suscriptor_id: UUID, plan: PlanSuscripcion) -> dict:
    now = datetime.now()
    inicio_mes = datetime(now.year, now.month, 1)

    plantillas_usadas = db.query(PlantillaEncuesta).filter(PlantillaEncuesta.suscriptor_id == suscriptor_id).count()
    campanas_activas = db.query(CampanaEncuesta).filter(
        CampanaEncuesta.suscriptor_id == suscriptor_id,
        CampanaEncuesta.estado_id != 5
    ).count()
    entregas_mes = (
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

    return {
        "plantillas_usadas": plantillas_usadas,
        "max_plantillas": plan.max_plantillas,
        "campanas_activas": campanas_activas,
        "max_campanas": plan.max_campanas,
        "entregas_mes": entregas_mes,
        "max_entregas": plan.max_entregas,
        "operadores_activos": operadores_activos,
        "max_operadores": plan.max_operadores
    }


# 1. LISTAR SUSCRIPTORES
@router.get("", response_model=List[SuscriptorListOut], summary="Listado general de empresas/suscriptores con su plan y uso")
def list_suscriptores_endpoint(db: Session = Depends(get_db)):
    suscriptores = db.query(Suscriptor).order_by(Suscriptor.creado_en.desc()).all()
    res = []

    for s in suscriptores:
        plan = get_plan_suscriptor(db, s.id)
        resumen_uso = _build_resumen_uso(db, s.id, plan)

        res.append({
            "id": s.id,
            "nombre_empresa": s.nombre,
            "email_contacto": s.email,
            "telefono": s.telefono,
            "estado": s.estado or "activo",
            "creado_en": s.creado_en or datetime.now(),
            "plan": {
                "id": plan.id,
                "nombre": plan.nombre,
                "precio_mensual": plan.precio_mensual
            },
            "resumen_uso": resumen_uso
        })

    return res


# 2. DETALLE 360 DE UN SUSCRIPTOR
@router.get("/{suscriptor_id}", response_model=SuscriptorDetail360Out, summary="Detalle 360 de la empresa con plan y cuotas")
def get_suscriptor_detail_endpoint(suscriptor_id: UUID, db: Session = Depends(get_db)):
    suscriptor = db.get(Suscriptor, suscriptor_id)
    if not suscriptor:
        raise HTTPException(status_code=404, detail="Suscriptor/Empresa no encontrado")

    plan = get_plan_suscriptor(db, suscriptor.id)
    resumen_uso = _build_resumen_uso(db, suscriptor.id, plan)

    suscripcion_activa = (
        db.query(SuscripcionSuscriptor)
        .filter(SuscripcionSuscriptor.suscriptor_id == suscriptor.id, SuscripcionSuscriptor.estado == "activo")
        .order_by(SuscripcionSuscriptor.inicia_en.desc())
        .first()
    )

    sub_activa_data = None
    if suscripcion_activa:
        sub_activa_data = {
            "id": suscripcion_activa.id,
            "inicia_en": suscripcion_activa.inicia_en,
            "expira_en": suscripcion_activa.expira_en,
            "estado": suscripcion_activa.estado
        }

    return {
        "id": suscriptor.id,
        "nombre_empresa": suscriptor.nombre,
        "email_contacto": suscriptor.email,
        "telefono": suscriptor.telefono,
        "estado": suscriptor.estado or "activo",
        "creado_en": suscriptor.creado_en or datetime.now(),
        "stripe_customer_id": suscriptor.stripe_customer_id,
        "suscripcion_activa": sub_activa_data,
        "plan": plan,
        "resumen_uso": resumen_uso
    }


# 3. HISTORIAL DE PAGOS DEL SUSCRIPTOR
@router.get("/{suscriptor_id}/pagos", response_model=List[PagoSuscriptorOut], summary="Historial de pagos de la empresa")
def get_suscriptor_pagos_endpoint(suscriptor_id: UUID, db: Session = Depends(get_db)):
    suscriptor = db.get(Suscriptor, suscriptor_id)
    if not suscriptor:
        raise HTTPException(status_code=404, detail="Suscriptor no encontrado")

    return (
        db.query(PagoSuscriptor)
        .filter(PagoSuscriptor.suscriptor_id == suscriptor_id)
        .order_by(PagoSuscriptor.fecha.desc())
        .all()
    )


# 4. OPERADORES DEL SUSCRIPTOR
@router.get("/{suscriptor_id}/operadores", response_model=List[OperadorOut], summary="Lista de operadores creados por la empresa")
def get_suscriptor_operadores_endpoint(suscriptor_id: UUID, db: Session = Depends(get_db)):
    suscriptor = db.get(Suscriptor, suscriptor_id)
    if not suscriptor:
        raise HTTPException(status_code=404, detail="Suscriptor no encontrado")

    operadores = (
        db.query(CuentaUsuario)
        .filter(CuentaUsuario.suscriptor_id == suscriptor_id, CuentaUsuario.role == "operator")
        .all()
    )

    return [
        {
            "id": op.id,
            "nombre_completo": op.nombre_completo,
            "email": op.email,
            "activo": op.activo,
            "creado_en": op.creado_en
        }
        for op in operadores
    ]


# 5. ACTUALIZAR ESTADO DEL SUSCRIPTOR
@router.put("/{suscriptor_id}/estado", response_model=SuscriptorDetail360Out, summary="Actualizar estado de la cuenta (activo | suspendido | pendiente)")
def update_suscriptor_estado_endpoint(
    suscriptor_id: UUID,
    payload: SuscriptorEstadoUpdate,
    db: Session = Depends(get_db)
):
    suscriptor = db.get(Suscriptor, suscriptor_id)
    if not suscriptor:
        raise HTTPException(status_code=404, detail="Suscriptor no encontrado")

    estado_lower = payload.estado.lower()
    if estado_lower not in ["activo", "suspendido", "pendiente"]:
        raise HTTPException(status_code=400, detail="Estado no válido. Valores permitidos: activo | suspendido | pendiente")

    suscriptor.estado = estado_lower
    db.commit()
    db.refresh(suscriptor)

    return get_suscriptor_detail_endpoint(suscriptor_id, db)


# 6. ASIGNAR / CAMBIAR PLAN MANULMENTE
@router.put("/{suscriptor_id}/asignar-plan", response_model=SuscriptorDetail360Out, summary="Asignar o cambiar de plan manualmente a la empresa")
def asignar_plan_suscriptor_endpoint(
    suscriptor_id: UUID,
    payload: SuscriptorAsignarPlan,
    db: Session = Depends(get_db)
):
    suscriptor = db.get(Suscriptor, suscriptor_id)
    if not suscriptor:
        raise HTTPException(status_code=404, detail="Suscriptor no encontrado")

    nuevo_plan = db.get(PlanSuscripcion, payload.plan_id)
    if not nuevo_plan:
        raise HTTPException(status_code=404, detail=f"Plan con ID {payload.plan_id} no encontrado")

    # Cancelar suscripciones previas activas
    suscripciones_viejas = (
        db.query(SuscripcionSuscriptor)
        .filter(SuscripcionSuscriptor.suscriptor_id == suscriptor_id, SuscripcionSuscriptor.estado == "activo")
        .all()
    )
    for sub_viej in suscripciones_viejas:
        sub_viej.estado = "cancelado"

    # Crear nueva suscripción activa
    nueva_sub = SuscripcionSuscriptor(
        suscriptor_id=suscriptor_id,
        plan_id=nuevo_plan.id,
        inicia_en=datetime.now(),
        estado="activo"
    )
    db.add(nueva_sub)
    db.commit()

    return get_suscriptor_detail_endpoint(suscriptor_id, db)
