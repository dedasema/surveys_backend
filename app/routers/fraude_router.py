# app/routers/fraude_router.py
import logging
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.fraude_flag import FraudeFlag
from app.models.survey import CampanaEncuesta, RespuestaEncuesta
from app.services.fraude_service import evaluar_respuesta_antifraude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fraude", tags=["Detección y Revisión de Fraude (RF21)"])

class ResolverFraudeInput(BaseModel):
    accion: str # 'confirmar_fraude', 'descartar_marca', 'confirmar', 'descartar'

@router.get("/cola", summary="Listar cola de respuestas marcadas para revisión de fraude (RF21)")
async def obtener_cola_fraude(
    campana_id: Optional[UUID] = Query(None),
    estado: Optional[str] = Query(None),
    tipo_senal: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(FraudeFlag)

    if campana_id:
        query = query.filter(FraudeFlag.campana_id == campana_id)
    if estado and estado != "todos":
        query = query.filter(FraudeFlag.estado == estado)
    if tipo_senal and tipo_senal != "todos":
        query = query.filter(FraudeFlag.tipo_senal == tipo_senal)

    flags = query.order_by(FraudeFlag.creado_en.desc()).all()

    return [
        {
            "id": str(f.id),
            "respuesta_id": str(f.respuesta_id),
            "campana_id": str(f.campana_id),
            "campana_nombre": f.campana.nombre if f.campana else "Campaña",
            "canal": f.canal,
            "tipo_senal": f.tipo_senal,
            "confianza": f.confianza,
            "contenido_respuesta": f.contenido_respuesta,
            "respuesta_similar": f.respuesta_similar,
            "similitud_score": f.similitud_score,
            "justificacion": f.justificacion,
            "timestamp": f.creado_en.isoformat() if f.creado_en else None,
            "estado": f.estado
        }
        for f in flags
    ]

@router.post("/{flag_id}/resolver", summary="Resolver una marca de fraude (confirmar o descartar) (RF21)")
async def resolver_marca_fraude(
    flag_id: UUID,
    payload: ResolverFraudeInput,
    db: Session = Depends(get_db)
):
    flag = db.query(FraudeFlag).filter(FraudeFlag.id == flag_id).first()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marca de fraude {flag_id} no encontrada"
        )

    accion = payload.accion.lower()
    if "confirmar" in accion:
        flag.estado = "confirmado_fraude"
    elif "descartar" in accion:
        flag.estado = "descartado_valido"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Acción '{payload.accion}' no reconocida. Use 'confirmar_fraude' o 'descartar_marca'"
        )

    db.commit()
    db.refresh(flag)

    return {
        "id": str(flag.id),
        "estado": flag.estado,
        "mensaje": f"Marca de fraude resuelta exitosamente como '{flag.estado}'"
    }

@router.post("/evaluar/{respuesta_id}", summary="Ejecutar análisis antifraude manual sobre una respuesta")
async def evaluar_respuesta_manual(
    respuesta_id: UUID,
    canal: str = Query("web"),
    db: Session = Depends(get_db)
):
    flag = await evaluar_respuesta_antifraude(db, respuesta_id, canal=canal)
    if not flag:
        return {
            "respuesta_id": str(respuesta_id),
            "es_sospechoso": False,
            "mensaje": "La respuesta no presenta indicios de fraude o duplicación anómala"
        }

    return {
        "respuesta_id": str(respuesta_id),
        "es_sospechoso": True,
        "flag_id": str(flag.id),
        "tipo_senal": flag.tipo_senal,
        "confianza": flag.confianza,
        "justificacion": flag.justificacion
    }
