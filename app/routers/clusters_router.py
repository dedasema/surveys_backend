# app/routers/clusters_router.py
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.survey import CampanaEncuesta
from app.services.clustering_service import agrupar_respuestas_en_clusters

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Clustering Semántico de Temas (RF22)"])

@router.get(
    "/campanas/{campana_id}/clusters",
    summary="Obtener clusters semánticos de respuestas para una campaña (RF22)"
)
async def obtener_clusters_campana(
    campana_id: UUID,
    db: Session = Depends(get_db)
):
    campana = db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()
    if not campana:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaña {campana_id} no encontrada"
        )

    clusters = await agrupar_respuestas_en_clusters(db=db, campana_id=campana_id)
    return {
        "campana_id": str(campana_id),
        "total_clusters": len(clusters),
        "clusters": clusters
    }

@router.post(
    "/campanas/{campana_id}/clusters/recalcular",
    summary="Recalcular clusters temáticos mediante embeddings y Gemini (RF22)"
)
async def recalcular_clusters_campana(
    campana_id: UUID,
    db: Session = Depends(get_db)
):
    campana = db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()
    if not campana:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaña {campana_id} no encontrada"
        )

    clusters = await agrupar_respuestas_en_clusters(db=db, campana_id=campana_id)
    return {
        "campana_id": str(campana_id),
        "mensaje": "Clusters semánticos recalculados exitosamente",
        "clusters": clusters
    }
