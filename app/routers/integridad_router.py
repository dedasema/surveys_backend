# app/routers/integridad_router.py
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_admin_user
from app.schemas.auth import TokenData
from app.services.hash_chain_service import verificar_integridad_cadena

router = APIRouter(
    prefix="/admin/integridad",
    tags=["Admin - Integridad de Datos (RNF8)"],
    dependencies=[Depends(get_admin_user)]
)

@router.get("/verificar", status_code=status.HTTP_200_OK)
def verificar_integridad_global_endpoint(
    db: Session = Depends(get_db),
    admin_data: TokenData = Depends(get_admin_user)
):
    """
    Verifica la integridad criptográfica de la cadena de bloques/hashes
    de todas las respuestas globales del sistema.
    """
    return verificar_integridad_cadena(db=db, campana_id=None)

@router.get("/verificar/{campana_id}", status_code=status.HTTP_200_OK)
def verificar_integridad_campana_endpoint(
    campana_id: UUID,
    db: Session = Depends(get_db),
    admin_data: TokenData = Depends(get_admin_user)
):
    """
    Verifica la integridad criptográfica de la cadena de hashes
    de una campaña específica. Detecta cualquier alteración manual de datos.
    """
    return verificar_integridad_cadena(db=db, campana_id=campana_id)
