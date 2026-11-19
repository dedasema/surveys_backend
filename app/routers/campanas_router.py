from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access
from app.core.security import require_acceso_suscriptor_activo
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData
from app.schemas.campanas_schema import CampanaCreate, CampanaOut, CampanaUpdate, CampanaDetailOut, CampanaFullDetailOut
from app.services.campanas_service import (
    create_campana, get_campana, list_campanas, update_campana, delete_campana,
    get_campana_full_detail, procesar_campanas_programadas,
    ESTADO_BORRADOR, ESTADO_PROGRAMADA, ESTADO_ENVIADA, ESTADO_CERRADA
)

router = APIRouter(
    prefix="/campanas",
    tags=["Campañas"]
)

@router.api_route("/procesar-programadas", methods=["GET", "POST"])
@router.api_route("/procesar-programada", methods=["GET", "POST"])
async def procesar_campanas_programadas_endpoint(
    db: Session = Depends(get_db)
):
    """
    Endpoint para procesar el envío automático de correos de campañas programadas.
    Acepta GET y POST, e URLs en singular o plural para flexibilidad total con cronjobs.
    """
    return await procesar_campanas_programadas(db)

@router.api_route("/{campana_id}/disparar", methods=["GET", "POST"])
@router.api_route("/{campana_id}/dispara", methods=["GET", "POST"])
async def disparar_campana_inmediata_endpoint(
    campana_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Dispara de inmediato el envío de todas las entregas pendientes de una campaña específica.
    """
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    campana.estado_id = ESTADO_PROGRAMADA
    db.commit()

    return await procesar_campanas_programadas(db)

@router.post("", response_model=CampanaOut, status_code=status.HTTP_201_CREATED)
async def create_campana_endpoint(
    payload: CampanaCreate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para crear campañas"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    from app.services.plan_limits_service import validate_campanas_limit, validate_canal_permission
    validate_campanas_limit(db, suscriptor_id)
    validate_canal_permission(db, suscriptor_id, payload.canal_id)

    return create_campana(db, payload, suscriptor_id)

@router.get("", response_model=List[CampanaOut])
async def list_campanas_endpoint(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para listar campañas"
        )
    
    suscriptor_id = UUID(token_data.sub) if token_data.role == "empresa" else (
        db.query(CuentaUsuario.suscriptor_id)
        .filter(CuentaUsuario.id == UUID(token_data.sub))
        .scalar()
    )
    
    return list_campanas(db, suscriptor_id)

@router.get("/{campana_id}", response_model=CampanaDetailOut)
async def get_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta campaña"
        )
    
    return campana

@router.get("/{campana_id}/exportar-excel")
@router.get("/{campana_id}/export-excel")
async def exportar_excel_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Exporta todas las respuestas y métricas de una campaña a un archivo Excel (.xlsx) estructurado.
    """
    from fastapi.responses import StreamingResponse
    from app.services.excel_export_service import generar_excel_respuestas_campana
    import urllib.parse

    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para exportar datos de esta campaña"
        )

    excel_stream = generar_excel_respuestas_campana(db, campana_id)
    filename = f"respuestas_{campana.nombre.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@router.patch("/{campana_id}", response_model=CampanaOut)
async def update_campana_endpoint(
    campana_id: UUID,
    payload: CampanaUpdate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    db: Session = Depends(get_db)
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para modificar esta campaña"
        )
    
    return update_campana(db, campana_id, payload)

@router.delete("/{campana_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para eliminar esta campaña"
        )
    
    delete_campana(db, campana_id)

@router.get("/{campana_id}/full-detail", response_model=CampanaFullDetailOut)
async def get_campana_full_detail_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene todos los detalles de una campaña incluyendo:
    - Información de la plantilla con sus preguntas y opciones
    - Todas las entregas con sus destinatarios
    - Todas las respuestas recibidas
    - Estadísticas generales
    """
    campana = get_campana_full_detail(db, campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    
    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta campaña"
        )
    
    return campana