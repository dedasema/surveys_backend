"""
FastAPI Router for Plantillas, Preguntas, and Opciones.
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access, require_acceso_suscriptor_activo
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData
from app.schemas.plantillas_schema import PlantillaCreate, PlantillaUpdate, PlantillaOut, PlantillaDetailOut
from app.schemas.preguntas_schema import PreguntaCreate, PreguntaUpdate, PreguntaOut, OpcionCreate, OpcionOut
from app.services.plan_limits_service import validate_plantillas_limit

from app.modules.plantillas.application.use_cases import (
    CreatePlantillaUseCase,
    GetPlantillaUseCase,
    ListPlantillasUseCase,
    UpdatePlantillaUseCase,
    DeletePlantillaUseCase,
)
from app.modules.plantillas.domain.entities import Pregunta, Opcion
from app.modules.plantillas.infrastructure.repositories import (
    SqlAlchemyPlantillaRepository,
    SqlAlchemyPreguntaRepository,
    SqlAlchemyOpcionRepository,
)

router = APIRouter(tags=["Plantillas"])


def get_plantilla_repo(db: Session = Depends(get_db)) -> SqlAlchemyPlantillaRepository:
    return SqlAlchemyPlantillaRepository(db)


def get_pregunta_repo(db: Session = Depends(get_db)) -> SqlAlchemyPreguntaRepository:
    return SqlAlchemyPreguntaRepository(db)


def get_opcion_repo(db: Session = Depends(get_db)) -> SqlAlchemyOpcionRepository:
    return SqlAlchemyOpcionRepository(db)


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


# ────────── Plantillas ──────────

@router.post("/plantillas", response_model=PlantillaOut, status_code=status.HTTP_201_CREATED)
async def create_plantilla_endpoint(
    payload: PlantillaCreate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    db: Session = Depends(get_db),
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(status_code=403, detail="No tiene permisos para crear plantillas")

    suscriptor_id = _resolve_suscriptor_id(token_data, db)
    validate_plantillas_limit(db, suscriptor_id)

    use_case = CreatePlantillaUseCase(repo)
    plantilla = use_case.execute(
        suscriptor_id=suscriptor_id,
        nombre=payload.nombre,
        descripcion=payload.descripcion,
    )
    return PlantillaOut(
        id=plantilla.id,
        suscriptor_id=plantilla.suscriptor_id,
        nombre=plantilla.nombre,
        descripcion=plantilla.descripcion,
        creado_en=plantilla.creado_en,
    )


@router.get("/plantillas", response_model=List[PlantillaOut])
async def list_plantillas_endpoint(
    token_data: TokenData = Depends(get_current_user),
    repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    db: Session = Depends(get_db),
):
    if token_data.role not in ["empresa", "operator"]:
        raise HTTPException(status_code=403, detail="No tiene permisos para listar plantillas")

    suscriptor_id = _resolve_suscriptor_id(token_data, db)
    use_case = ListPlantillasUseCase(repo)
    plantillas = use_case.execute(suscriptor_id)
    return [
        PlantillaOut(
            id=p.id,
            suscriptor_id=p.suscriptor_id,
            nombre=p.nombre,
            descripcion=p.descripcion,
            creado_en=p.creado_en,
        )
        for p in plantillas
    ]


@router.get("/plantillas/{plantilla_id}", response_model=PlantillaDetailOut)
async def get_plantilla_endpoint(
    plantilla_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    db: Session = Depends(get_db),
):
    use_case = GetPlantillaUseCase(repo)
    plantilla = use_case.execute(plantilla_id, con_preguntas=True)

    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para ver esta plantilla")

    return PlantillaDetailOut(
        id=plantilla.id,
        suscriptor_id=plantilla.suscriptor_id,
        nombre=plantilla.nombre,
        descripcion=plantilla.descripcion,
        creado_en=plantilla.creado_en,
        preguntas=[
            {
                "id": p.id,
                "plantilla_id": p.plantilla_id,
                "texto": p.texto,
                "tipo_pregunta_id": p.tipo_pregunta_id,
                "obligatorio": p.obligatorio,
                "orden": p.orden,
                "opciones": [{"id": o.id, "pregunta_id": o.pregunta_id, "texto": o.texto, "valor": o.valor} for o in p.opciones],
            }
            for p in plantilla.preguntas
        ],
    )


@router.patch("/plantillas/{plantilla_id}", response_model=PlantillaOut)
async def update_plantilla_endpoint(
    plantilla_id: UUID,
    payload: PlantillaUpdate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    db: Session = Depends(get_db),
):
    use_case = GetPlantillaUseCase(repo)
    plantilla = use_case.execute(plantilla_id)

    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para modificar esta plantilla")

    update_use_case = UpdatePlantillaUseCase(repo)
    updated = update_use_case.execute(
        plantilla_id=plantilla_id,
        nombre=payload.nombre,
        descripcion=payload.descripcion,
    )
    return PlantillaOut(
        id=updated.id,
        suscriptor_id=updated.suscriptor_id,
        nombre=updated.nombre,
        descripcion=updated.descripcion,
        creado_en=updated.creado_en,
    )


@router.delete("/plantillas/{plantilla_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plantilla_endpoint(
    plantilla_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    db: Session = Depends(get_db),
):
    use_case = GetPlantillaUseCase(repo)
    plantilla = use_case.execute(plantilla_id)

    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para eliminar esta plantilla")

    delete_use_case = DeletePlantillaUseCase(repo)
    delete_use_case.execute(plantilla_id)


# ────────── Preguntas ──────────

@router.post("/plantillas/{plantilla_id}/preguntas", response_model=PreguntaOut, status_code=status.HTTP_201_CREATED)
async def create_pregunta_endpoint(
    plantilla_id: UUID,
    payload: PreguntaCreate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para acceder a esta plantilla")

    pregunta = Pregunta(
        id=UUID(int=0), # ID will be generated in domain
        plantilla_id=plantilla_id,
        texto=payload.texto,
        tipo_pregunta_id=payload.tipo_pregunta_id,
        obligatorio=payload.obligatorio,
        orden=payload.orden or 1,
    )
    saved = pregunta_repo.save(pregunta)
    return PreguntaOut(
        id=saved.id,
        plantilla_id=saved.plantilla_id,
        texto=saved.texto,
        tipo_pregunta_id=saved.tipo_pregunta_id,
        obligatorio=saved.obligatorio,
        orden=saved.orden,
        opciones=[],
    )


@router.get("/plantillas/{plantilla_id}/preguntas", response_model=List[PreguntaOut])
async def list_preguntas_endpoint(
    plantilla_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para acceder a esta plantilla")

    preguntas = pregunta_repo.list_by_plantilla(plantilla_id)
    return [
        PreguntaOut(
            id=p.id,
            plantilla_id=p.plantilla_id,
            texto=p.texto,
            tipo_pregunta_id=p.tipo_pregunta_id,
            obligatorio=p.obligatorio,
            orden=p.orden,
            opciones=[{"id": o.id, "pregunta_id": o.pregunta_id, "texto": o.texto, "valor": o.valor} for o in p.opciones],
        )
        for p in preguntas
    ]


@router.get("/plantillas/{plantilla_id}/preguntas/{pregunta_id}", response_model=PreguntaOut)
async def get_pregunta_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para acceder a esta plantilla")

    pregunta = pregunta_repo.get_by_id(pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    return PreguntaOut(
        id=pregunta.id,
        plantilla_id=pregunta.plantilla_id,
        texto=pregunta.texto,
        tipo_pregunta_id=pregunta.tipo_pregunta_id,
        obligatorio=pregunta.obligatorio,
        orden=pregunta.orden,
        opciones=[{"id": o.id, "pregunta_id": o.pregunta_id, "texto": o.texto, "valor": o.valor} for o in pregunta.opciones],
    )


@router.patch("/plantillas/{plantilla_id}/preguntas/{pregunta_id}", response_model=PreguntaOut)
async def update_pregunta_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    payload: PreguntaUpdate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para modificar esta plantilla")

    pregunta = pregunta_repo.get_by_id(pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    update_data = payload.model_dump(exclude_unset=True)
    if "texto" in update_data:
        pregunta.texto = update_data["texto"]
    if "tipo_pregunta_id" in update_data:
        pregunta.tipo_pregunta_id = update_data["tipo_pregunta_id"]
    if "obligatorio" in update_data:
        pregunta.obligatorio = update_data["obligatorio"]
    if "orden" in update_data:
        pregunta.orden = update_data["orden"]

    saved = pregunta_repo.save(pregunta)
    return PreguntaOut(
        id=saved.id,
        plantilla_id=saved.plantilla_id,
        texto=saved.texto,
        tipo_pregunta_id=saved.tipo_pregunta_id,
        obligatorio=saved.obligatorio,
        orden=saved.orden,
        opciones=[{"id": o.id, "pregunta_id": o.pregunta_id, "texto": o.texto, "valor": o.valor} for o in saved.opciones],
    )


@router.delete("/plantillas/{plantilla_id}/preguntas/{pregunta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pregunta_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para eliminar preguntas de esta plantilla")

    pregunta = pregunta_repo.get_by_id(pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    pregunta_repo.delete(pregunta_id)


# ────────── Opciones ──────────

@router.post("/plantillas/{plantilla_id}/preguntas/{pregunta_id}/opciones", response_model=OpcionOut, status_code=status.HTTP_201_CREATED)
async def create_opcion_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    payload: OpcionCreate,
    token_data: TokenData = Depends(get_current_user),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    opcion_repo: SqlAlchemyOpcionRepository = Depends(get_opcion_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para acceder a esta plantilla")

    pregunta = pregunta_repo.get_by_id(pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    opcion = Opcion(
        id=UUID(int=0),
        pregunta_id=pregunta_id,
        texto=payload.texto,
        valor=payload.valor,
    )
    saved = opcion_repo.save(opcion)
    return OpcionOut(
        id=saved.id,
        pregunta_id=saved.pregunta_id,
        texto=saved.texto,
        valor=saved.valor,
    )


@router.get("/plantillas/{plantilla_id}/preguntas/{pregunta_id}/opciones", response_model=List[OpcionOut])
async def list_opciones_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    opcion_repo: SqlAlchemyOpcionRepository = Depends(get_opcion_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para acceder a esta plantilla")

    pregunta = pregunta_repo.get_by_id(pregunta_id)
    if not pregunta or pregunta.plantilla_id != plantilla_id:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    opciones = opcion_repo.list_by_pregunta(pregunta_id)
    return [
        OpcionOut(
            id=o.id,
            pregunta_id=o.pregunta_id,
            texto=o.texto,
            valor=o.valor,
        )
        for o in opciones
    ]


@router.delete("/plantillas/{plantilla_id}/preguntas/{pregunta_id}/opciones/{opcion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opcion_endpoint(
    plantilla_id: UUID,
    pregunta_id: UUID,
    opcion_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    plantilla_repo: SqlAlchemyPlantillaRepository = Depends(get_plantilla_repo),
    pregunta_repo: SqlAlchemyPreguntaRepository = Depends(get_pregunta_repo),
    opcion_repo: SqlAlchemyOpcionRepository = Depends(get_opcion_repo),
    db: Session = Depends(get_db),
):
    plantilla = GetPlantillaUseCase(plantilla_repo).execute(plantilla_id)
    if not await validate_subscriber_access(token_data, plantilla.suscriptor_id, db):
        raise HTTPException(status_code=403, detail="No tiene permisos para eliminar opciones de esta plantilla")

    opcion = opcion_repo.get_by_id(opcion_id)
    if not opcion or opcion.pregunta_id != pregunta_id:
        raise HTTPException(status_code=404, detail="Opción no encontrada")

    opcion_repo.delete(opcion_id)
