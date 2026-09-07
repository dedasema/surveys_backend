# app/routers/predictivo_router.py
import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.survey import CampanaEncuesta
from app.models.agregado_campana import AgregadoCampana
from app.services.predictivo_service import obtener_metricas_predictivas

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dashboard Predictivo (RF23)"])

class AgregadoCreateInput(BaseModel):
    periodo: str
    total_respuestas: int
    promedio_satisfaccion: float
    tasa_completitud: float = 100.0
    orden_periodo: int = 1

@router.get("/campanas/{campana_id}/predictivo", summary="Obtener métricas y proyección predictiva de campaña (RF23)")
async def obtener_predictivo_campana(
    campana_id: UUID,
    metrica: str = Query("respuestas", pattern="^(respuestas|satisfaccion)$"),
    granularidad: str = Query("semanal", pattern="^(semanal|mensual)$"),
    db: Session = Depends(get_db)
):
    campana = db.query(CampanaEncuesta).filter_by(id=campana_id).first()
    if not campana:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaña {campana_id} no encontrada"
        )

    return await obtener_metricas_predictivas(
        db=db,
        campana_id=campana_id,
        metrica=metrica,
        granularidad=granularidad
    )

@router.get("/predictivo", summary="Obtener métricas y proyecciones predictivas globales (RF23)")
async def obtener_predictivo_global(
    metrica: str = Query("respuestas", pattern="^(respuestas|satisfaccion)$"),
    granularidad: str = Query("semanal", pattern="^(semanal|mensual)$"),
    db: Session = Depends(get_db)
):
    return await obtener_metricas_predictivas(
        db=db,
        campana_id=None,
        metrica=metrica,
        granularidad=granularidad
    )

@router.post("/campanas/{campana_id}/agregados", status_code=status.HTTP_201_CREATED, summary="Registrar cohorte de agregados históricos para una campaña")
async def registrar_agregado_campana(
    campana_id: UUID,
    payload: AgregadoCreateInput,
    db: Session = Depends(get_db)
):
    campana = db.query(CampanaEncuesta).filter_by(id=campana_id).first()
    if not campana:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaña {campana_id} no encontrada"
        )

    agregado = AgregadoCampana(
        campana_id=campana_id,
        periodo=payload.periodo,
        total_respuestas=payload.total_respuestas,
        promedio_satisfaccion=payload.promedio_satisfaccion,
        tasa_completitud=payload.tasa_completitud,
        orden_periodo=payload.orden_periodo
    )
    db.add(agregado)
    db.commit()
    db.refresh(agregado)

    return {
        "id": str(agregado.id),
        "campana_id": str(agregado.campana_id),
        "periodo": agregado.periodo,
        "total_respuestas": agregado.total_respuestas,
        "promedio_satisfaccion": agregado.promedio_satisfaccion,
        "orden_periodo": agregado.orden_periodo
    }
