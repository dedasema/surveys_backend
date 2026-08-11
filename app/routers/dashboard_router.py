from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict
from uuid import UUID

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.schemas.auth import TokenData

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

# Lazy instantiation to avoid importing openai at module load
_dashboard_service = None

def _get_dashboard_service():
    global _dashboard_service
    if _dashboard_service is None:
        from app.services.dashboard_service import DashboardService
        _dashboard_service = DashboardService()
    return _dashboard_service

@router.get("/campaigns/{campaign_id}/analysis")
async def get_campaign_analysis(
    campaign_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict:
    """
    Endpoint para obtener análisis detallado de una campaña usando GPT-4
    """
    try:
        if token_data.role not in ["admin", "empresa"]:
            raise HTTPException(
                status_code=403,
                detail="No tienes permisos para acceder a este análisis"
            )

        # Obtener análisis
        dashboard_service = _get_dashboard_service()
        analysis = await dashboard_service.get_campaign_analysis(db, campaign_id)
        
        return analysis

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo análisis de campaña: {str(e)}"
        )