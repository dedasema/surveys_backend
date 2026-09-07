# app/routers/rag_router.py
import logging
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.rag_consulta import RagConsulta
from app.services.rag_service import consultar_asistente_rag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/asistente", tags=["Asistente RAG de Consultas (RF26)"])

class RagConsultaInput(BaseModel):
    pregunta: str
    campana_id: Optional[UUID] = None

@router.post("/consultar", status_code=status.HTTP_200_OK, summary="Consultar al asistente RAG con fundamentación de fuentes (RF26)")
async def consultar_asistente(
    payload: RagConsultaInput,
    db: Session = Depends(get_db)
):
    resultado = await consultar_asistente_rag(
        db=db,
        pregunta=payload.pregunta,
        campana_id=payload.campana_id
    )
    return resultado

@router.get("/historial", summary="Consultar historial de preguntas y respuestas del asistente RAG (RF26)")
async def obtener_historial_rag(
    campana_id: Optional[UUID] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(RagConsulta)
    if campana_id:
        query = query.filter(RagConsulta.campana_id == campana_id)

    registros = query.order_by(RagConsulta.creado_en.desc()).limit(limit).all()

    return [
        {
            "id": str(r.id),
            "pregunta": r.pregunta,
            "respuesta": r.respuesta,
            "campana_id": str(r.campana_id) if r.campana_id else None,
            "fuentes_citadas": r.fuentes_citadas or [],
            "timestamp": r.creado_en.isoformat() if r.creado_en else None
        }
        for r in registros
    ]
