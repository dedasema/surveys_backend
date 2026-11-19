"""
FastAPI Router for Campanas (Inbound Adapter).
Translates HTTP requests to Application Use Cases and Domain Entities.
"""

from typing import List
from uuid import UUID
from datetime import datetime
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    get_current_user,
    validate_subscriber_access,
    require_acceso_suscriptor_activo,
)
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData

from app.modules.campanas.application.dtos import CreateCampanaCommand, UpdateCampanaCommand
from app.modules.campanas.application.use_cases import (
    CreateCampanaUseCase,
    ListCampanasUseCase,
    UpdateCampanaUseCase,
    DeleteCampanaUseCase,
)
from app.modules.campanas.domain.entities import EstadoCampanaEnum
from app.modules.campanas.infrastructure.repositories import SqlAlchemyCampanaRepository
from app.modules.campanas.infrastructure.schemas import (
    CampanaCreate,
    CampanaUpdate,
    CampanaOut,
    CampanaDetailOut,
    CampanaFullDetailOut,
)
from app.schemas.respuestas_schema import RespuestaListItemOut

# Services for specialized side-effects (e.g. background delivery, excel export)
from app.services.campanas_service import (
    get_campana as legacy_get_campana,
    get_campana_full_detail,
    procesar_campanas_programadas,
)
from app.services.excel_export_service import generar_excel_respuestas_campana
from app.services.plan_limits_service import validate_campanas_limit, validate_canal_permission

router = APIRouter(prefix="/campanas", tags=["Campañas"])


def get_repository(db: Session = Depends(get_db)) -> SqlAlchemyCampanaRepository:
    return SqlAlchemyCampanaRepository(db)


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
            detail="No se encontró una empresa asociada a este usuario.",
        )
    return suscriptor_id


@router.api_route("/procesar-programadas", methods=["GET", "POST"])
@router.api_route("/procesar-programada", methods=["GET", "POST"])
async def procesar_campanas_programadas_endpoint(db: Session = Depends(get_db)):
    """Endpoint para procesar el envío automático de correos de campañas programadas."""
    return await procesar_campanas_programadas(db)


@router.api_route("/{campana_id}/disparar", methods=["GET", "POST"])
@router.api_route("/{campana_id}/dispara", methods=["GET", "POST"])
async def disparar_campana_inmediata_endpoint(
    campana_id: UUID,
    repo: SqlAlchemyCampanaRepository = Depends(get_repository),
    db: Session = Depends(get_db),
):
    """Dispara de inmediato el envío de todas las entregas pendientes de una campaña específica."""
    campana = repo.get_by_id(campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    campana.estado_id = EstadoCampanaEnum.PROGRAMADA
    repo.save(campana)

    return await procesar_campanas_programadas(db)


@router.post("", response_model=CampanaOut, status_code=status.HTTP_201_CREATED)
async def create_campana_endpoint(
    payload: CampanaCreate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    repo: SqlAlchemyCampanaRepository = Depends(get_repository),
    db: Session = Depends(get_db),
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para crear campañas",
        )

    suscriptor_id = _resolve_suscriptor_id(token_data, db)
    validate_campanas_limit(db, suscriptor_id)
    validate_canal_permission(db, suscriptor_id, payload.canal_id)

    use_case = CreateCampanaUseCase(repo)
    command = CreateCampanaCommand(
        suscriptor_id=suscriptor_id,
        nombre=payload.nombre,
        canal_id=payload.canal_id,
        plantilla_id=payload.plantilla_id,
        programada_en=payload.programada_en,
    )
    campana = use_case.execute(command)

    return CampanaOut(
        id=campana.id,
        suscriptor_id=campana.suscriptor_id,
        nombre=campana.nombre,
        plantilla_id=campana.plantilla_id,
        canal_id=campana.canal_id,
        programada_en=campana.programada_en,
        estado_id=campana.estado_id,
        creado_en=campana.creado_en or datetime.utcnow(),
    )


@router.get("", response_model=List[CampanaOut])
async def list_campanas_endpoint(
    token_data: TokenData = Depends(get_current_user),
    repo: SqlAlchemyCampanaRepository = Depends(get_repository),
    db: Session = Depends(get_db),
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para listar campañas",
        )

    suscriptor_id = _resolve_suscriptor_id(token_data, db)
    use_case = ListCampanasUseCase(repo)
    campanas = use_case.execute(suscriptor_id)

    return [
        CampanaOut(
            id=c.id,
            suscriptor_id=c.suscriptor_id,
            nombre=c.nombre,
            plantilla_id=c.plantilla_id,
            canal_id=c.canal_id,
            programada_en=c.programada_en,
            estado_id=c.estado_id,
            creado_en=c.creado_en or datetime.utcnow(),
        )
        for c in campanas
    ]


@router.get("/{campana_id}", response_model=CampanaDetailOut)
async def get_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campana_orm = legacy_get_campana(db, campana_id)
    if not campana_orm:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    if not await validate_subscriber_access(token_data, campana_orm.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta campaña",
        )

    return campana_orm


@router.get("/{campana_id}/exportar-excel")
@router.get("/{campana_id}/export-excel")
async def exportar_excel_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    repo: SqlAlchemyCampanaRepository = Depends(get_repository),
    db: Session = Depends(get_db),
):
    campana = repo.get_by_id(campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para exportar datos de esta campaña",
        )

    excel_stream = generar_excel_respuestas_campana(db, campana_id)
    clean_nombre = campana.nombre.replace(" ", "_")
    filename = f"respuestas_{clean_nombre}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{campana_id}/respuestas", response_model=List[RespuestaListItemOut])
async def list_campana_respuestas_endpoint(
    campana_id: UUID,
    skip: int = 0,
    limit: int = 500,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.modules.respuestas.infrastructure.router import list_all_respuestas_endpoint
    return await list_all_respuestas_endpoint(
        campana_id=campana_id,
        skip=skip,
        limit=limit,
        token_data=token_data,
        db=db,
    )


@router.patch("/{campana_id}", response_model=CampanaOut)
async def update_campana_endpoint(
    campana_id: UUID,
    payload: CampanaUpdate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    repo: SqlAlchemyCampanaRepository = Depends(get_repository),
    db: Session = Depends(get_db),
):
    campana = repo.get_by_id(campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para modificar esta campaña",
        )

    use_case = UpdateCampanaUseCase(repo)
    command = UpdateCampanaCommand(
        campana_id=campana_id,
        suscriptor_id=campana.suscriptor_id,
        nombre=payload.nombre,
        plantilla_id=payload.plantilla_id,
        canal_id=payload.canal_id,
        estado_id=payload.estado_id,
        programada_en=payload.programada_en,
    )
    updated = use_case.execute(command)

    return CampanaOut(
        id=updated.id,
        suscriptor_id=updated.suscriptor_id,
        nombre=updated.nombre,
        plantilla_id=updated.plantilla_id,
        canal_id=updated.canal_id,
        programada_en=updated.programada_en,
        estado_id=updated.estado_id,
        creado_en=updated.creado_en or datetime.utcnow(),
    )


@router.delete("/{campana_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campana_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    repo: SqlAlchemyCampanaRepository = Depends(get_repository),
    db: Session = Depends(get_db),
):
    campana = repo.get_by_id(campana_id)
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para eliminar esta campaña",
        )

    use_case = DeleteCampanaUseCase(repo)
    use_case.execute(campana_id)


@router.get("/{campana_id}/full-detail", response_model=CampanaFullDetailOut)
async def get_campana_full_detail_endpoint(
    campana_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    campana_detail = get_campana_full_detail(db, campana_id)
    if not campana_detail:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    if not await validate_subscriber_access(token_data, campana_detail.suscriptor_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta campaña",
        )

    return campana_detail
