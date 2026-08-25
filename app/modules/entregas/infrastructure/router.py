"""
FastAPI Router for Entregas and Destinatarios.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access, require_acceso_suscriptor_activo
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData
from app.schemas.destinatarios_schema import DestinarioCreate, DestinarioUpdate, DestinarioOut
from app.schemas.entregas_schema import EntregaCreate, EntregaUpdate, EntregaOut, EntregaDetailOut, EntregaPublicaOut

from app.modules.entregas.infrastructure.repositories import (
    SqlAlchemyEntregaRepository,
    SqlAlchemyDestinatarioRepository,
)
from app.services.campanas_service import get_campana
from app.services.entregas_service import (
    create_entrega,
    create_bulk_entregas_audio,
    create_bulk_entregas_papel,
    get_entrega,
    list_entregas,
    update_entrega,
    delete_entrega,
    get_entrega_con_plantilla,
)
from app.services.destinatarios_service import (
    create_destinatario,
    get_destinatario,
    list_destinatarios,
    update_destinatario,
    delete_destinatario,
    process_excel_destinatarios,
)

entregas_router = APIRouter(prefix="/campanas/{campana_id}/entregas", tags=["Entregas"])
public_entregas_router = APIRouter(prefix="/public/entregas", tags=["Entregas Públicas"])
destinatarios_router = APIRouter(prefix="/destinatarios", tags=["Destinatarios"])


def _resolve_suscriptor_id(token_data: TokenData, db: Session) -> UUID:
    if token_data.role == "empresa":
        return UUID(token_data.sub)
    suscriptor_id = (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    if not suscriptor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se encontró empresa asociada al usuario",
        )
    return suscriptor_id


# ────────── Entregas ──────────

@entregas_router.post("", response_model=EntregaOut, status_code=status.HTTP_201_CREATED)
async def create_entrega_endpoint(
    campana_id: UUID,
    payload: EntregaCreate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    db: Session = Depends(get_db),
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos sobre esta campaña")
    return create_entrega(db, campana_id, payload)


@entregas_router.get("", response_model=List[EntregaDetailOut])
async def list_entregas_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos sobre esta campaña")
    return list_entregas(db, campana_id)


@entregas_router.get("/{entrega_id}", response_model=EntregaDetailOut)
async def get_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos sobre esta campaña")
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    return entrega


@entregas_router.delete("/{entrega_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos sobre esta campaña")
    delete_entrega(db, entrega_id)


# ────────── Destinatarios ──────────

@destinatarios_router.post("", response_model=DestinarioOut, status_code=status.HTTP_201_CREATED)
async def create_destinatario_endpoint(
    payload: DestinarioCreate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    db: Session = Depends(get_db),
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(status_code=403, detail="No tiene permisos para crear destinatarios")
    suscriptor_id = _resolve_suscriptor_id(token_data, db)
    return create_destinatario(db, suscriptor_id, payload)


@destinatarios_router.get("", response_model=List[DestinarioOut])
async def list_destinatarios_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, le=1000),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(status_code=403, detail="No tiene permisos para listar destinatarios")
    suscriptor_id = _resolve_suscriptor_id(token_data, db)
    return list_destinatarios(db, suscriptor_id, skip=skip, limit=limit)


@destinatarios_router.delete("/{destinatario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_destinatario_endpoint(
    destinatario_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suscriptor_id = _resolve_suscriptor_id(token_data, db)
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario or destinatario.suscriptor_id != suscriptor_id:
        raise HTTPException(status_code=404, detail="Destinatario no encontrado")
    delete_destinatario(db, destinatario_id)
