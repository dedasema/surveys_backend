# app/routers/archivos_router.py
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.models.cuenta_usuario import CuentaUsuario
from app.models.suscriptor import Suscriptor
from app.schemas.archivos import ArchivosListResponse, ArchivoItemOut
from app.services.archivos_service import (
    listar_archivos_empresa,
    subir_archivo_empresa,
    eliminar_archivo_empresa
)

router = APIRouter(
    prefix="/archivos",
    tags=["Archivos"],
    dependencies=[Depends(get_current_user)]
)

empresa_alias_router = APIRouter(
    prefix="/empresa/archivos",
    tags=["Archivos"],
    dependencies=[Depends(get_current_user)]
)

def _resolver_suscriptor_id(
    db: Session,
    token_data: TokenData,
    suscriptor_id_param: Optional[UUID] = None
) -> UUID:
    """Resuelve el tenant de acuerdo al rol del token."""
    if token_data.role == "empresa":
        return UUID(token_data.sub)
    elif token_data.role in ["operator", "empresa_operador"]:
        cuenta = db.query(CuentaUsuario).filter(CuentaUsuario.id == UUID(token_data.sub)).first()
        if not cuenta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta de usuario no encontrada")
        return cuenta.suscriptor_id
    elif token_data.role == "admin":
        if suscriptor_id_param:
            return suscriptor_id_param
        primer_sus = db.query(Suscriptor).first()
        if not primer_sus:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existen empresas registradas")
        return primer_sus.id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para acceder a estos archivos")

@router.get("", response_model=ArchivosListResponse)
@empresa_alias_router.get("", response_model=ArchivosListResponse)
def get_archivos_empresa(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría (audio_respuesta, avatar, documento)"),
    busqueda: Optional[str] = Query(None, description="Buscar por nombre, extensión o contexto"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad de registros por página"),
    offset: int = Query(0, ge=0, description="Desplazamiento inicial"),
    suscriptor_id: Optional[UUID] = Query(None, description="ID del suscriptor (solo para rol admin)"),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos los archivos pertenecientes a la empresa (audios de encuestas, avatares y documentos)
    con metadatos completos: nombre, extensión, peso, unidad, URL de vista/descarga, tipo mime y contexto.
    """
    tenant_id = _resolver_suscriptor_id(db, token_data, suscriptor_id)
    total, items, espacio_mb = listar_archivos_empresa(
        db=db,
        suscriptor_id=tenant_id,
        categoria=categoria,
        busqueda=busqueda,
        limit=limit,
        offset=offset
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "espacio_total_usado_mb": espacio_mb,
        "archivos": items
    }

@router.post("/upload", response_model=ArchivoItemOut, status_code=status.HTTP_201_CREATED)
@empresa_alias_router.post("/upload", response_model=ArchivoItemOut, status_code=status.HTTP_201_CREATED)
async def upload_archivo_empresa(
    file: UploadFile = File(...),
    categoria: str = Form("documento"),
    contexto: Optional[str] = Form(None),
    suscriptor_id: Optional[UUID] = Form(None),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sube un archivo a la empresa, calcula su peso real y lo almacena registrándolo en la bitácora.
    """
    tenant_id = _resolver_suscriptor_id(db, token_data, suscriptor_id)
    email_usuario = getattr(token_data, "email", None) or token_data.sub

    resultado = await subir_archivo_empresa(
        db=db,
        suscriptor_id=tenant_id,
        file=file,
        categoria=categoria,
        contexto=contexto,
        usuario_email=email_usuario
    )
    return resultado

@router.delete("/{archivo_id}", status_code=status.HTTP_200_OK)
@empresa_alias_router.delete("/{archivo_id}", status_code=status.HTTP_200_OK)
def delete_archivo_empresa(
    archivo_id: UUID,
    suscriptor_id: Optional[UUID] = Query(None),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Elimina físicamente y de la base de datos un archivo de la empresa, liberando cuota.
    """
    tenant_id = _resolver_suscriptor_id(db, token_data, suscriptor_id)
    email_usuario = getattr(token_data, "email", None) or token_data.sub

    eliminado = eliminar_archivo_empresa(
        db=db,
        suscriptor_id=tenant_id,
        archivo_id=archivo_id,
        usuario_email=email_usuario
    )
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo no encontrado o no pertenece a esta empresa"
        )
    return {"mensaje": "Archivo eliminado correctamente", "archivo_id": str(archivo_id)}
