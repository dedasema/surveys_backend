# app/routers/agente_router.py
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.agente_decision import AgenteDecision
from app.models.survey import CampanaEncuesta
from app.services.agente_service import evaluar_evento_con_agente

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agente", tags=["Agente Autónomo y Decision Log (RF25)"])

class EvaluarEventoInput(BaseModel):
    campana_id: UUID
    trigger_evento: str
    respuesta_id: Optional[UUID] = None
    contexto_adicional: Optional[Dict[str, Any]] = None

@router.get("/decisiones", summary="Consultar historial y traza de decisiones del agente autónomo (RF25)")
async def obtener_decisiones_agente(
    campana_id: Optional[UUID] = Query(None),
    tool: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(AgenteDecision)

    if campana_id:
        query = query.filter(AgenteDecision.campana_id == campana_id)
    if tool and tool != "todos":
        query = query.filter(AgenteDecision.tool_ejecutada == tool)
    if estado and estado != "todos":
        query = query.filter(AgenteDecision.estado == estado)

    decisiones = query.order_by(AgenteDecision.creado_en.desc()).all()

    return [
        {
            "id": str(d.id),
            "timestamp": d.creado_en.isoformat() if d.creado_en else None,
            "campana_id": str(d.campana_id),
            "campana_nombre": d.campana_nombre or (d.campana.nombre if d.campana else "Campaña"),
            "trigger_evento": d.trigger_evento,
            "respuesta_id": str(d.respuesta_id) if d.respuesta_id else None,
            "tool_ejecutada": d.tool_ejecutada,
            "parametros": d.parametros or {},
            "razonamiento_ia": d.razonamiento_ia,
            "estado": d.estado,
            "tiempo_ejecucion_ms": d.tiempo_ejecucion_ms
        }
        for d in decisiones
    ]

@router.post("/evaluar", status_code=status.HTTP_201_CREATED, summary="Disparar evaluación y ejecución de tools del agente (RF25)")
async def disparar_evaluacion_agente(
    payload: EvaluarEventoInput,
    db: Session = Depends(get_db)
):
    campana = db.query(CampanaEncuesta).filter_by(id=payload.campana_id).first()
    if not campana:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaña {payload.campana_id} no encontrada"
        )

    decision = await evaluar_evento_con_agente(
        db=db,
        campana_id=payload.campana_id,
        trigger_evento=payload.trigger_evento,
        respuesta_id=payload.respuesta_id,
        contexto_adicional=payload.contexto_adicional
    )

    return {
        "id": str(decision.id),
        "timestamp": decision.creado_en.isoformat() if decision.creado_en else None,
        "campana_id": str(decision.campana_id),
        "campana_nombre": decision.campana_nombre,
        "trigger_evento": decision.trigger_evento,
        "respuesta_id": str(decision.respuesta_id) if decision.respuesta_id else None,
        "tool_ejecutada": decision.tool_ejecutada,
        "parametros": decision.parametros or {},
        "razonamiento_ia": decision.razonamiento_ia,
        "estado": decision.estado,
        "tiempo_ejecucion_ms": decision.tiempo_ejecucion_ms
    }
