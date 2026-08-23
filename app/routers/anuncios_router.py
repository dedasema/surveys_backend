from typing import List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_admin_user, get_current_user
from app.models.anuncio_sistema import AnuncioSistema
from app.schemas.anuncio_sistema_schema import (
    AnuncioSistemaCreate,
    AnuncioSistemaUpdate,
    AnuncioSistemaOut
)

admin_router = APIRouter(
    prefix="/admin/anuncios",
    tags=["Admin - Anuncios del Sistema"],
    dependencies=[Depends(get_admin_user)]
)

public_router = APIRouter(
    prefix="/anuncios",
    tags=["Anuncios del Sistema"]
)

# --- RUTAS DE SUPERADMIN ---

@admin_router.post("", response_model=AnuncioSistemaOut, status_code=status.HTTP_201_CREATED, summary="Crear un anuncio global del sistema")
def create_anuncio_endpoint(payload: AnuncioSistemaCreate, db: Session = Depends(get_db)):
    anuncio = AnuncioSistema(
        titulo=payload.titulo,
        mensaje=payload.mensaje,
        tipo=payload.tipo,
        activo=payload.activo
    )
    db.add(anuncio)
    db.commit()
    db.refresh(anuncio)
    return anuncio


@admin_router.get("", response_model=List[AnuncioSistemaOut], summary="Listar todos los anuncios del sistema")
def list_anuncios_admin_endpoint(db: Session = Depends(get_db)):
    return db.query(AnuncioSistema).order_by(AnuncioSistema.creado_en.desc()).all()


@admin_router.put("/{anuncio_id}", response_model=AnuncioSistemaOut, summary="Editar o cambiar estado de un anuncio")
def update_anuncio_endpoint(anuncio_id: UUID, payload: AnuncioSistemaUpdate, db: Session = Depends(get_db)):
    anuncio = db.get(AnuncioSistema, anuncio_id)
    if not anuncio:
        raise HTTPException(status_code=404, detail="Anuncio no encontrado")

    if payload.titulo is not None:
        anuncio.titulo = payload.titulo
    if payload.mensaje is not None:
        anuncio.mensaje = payload.mensaje
    if payload.tipo is not None:
        anuncio.tipo = payload.tipo
    if payload.activo is not None:
        anuncio.activo = payload.activo

    db.commit()
    db.refresh(anuncio)
    return anuncio


@admin_router.delete("/{anuncio_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar un anuncio")
def delete_anuncio_endpoint(anuncio_id: UUID, db: Session = Depends(get_db)):
    anuncio = db.get(AnuncioSistema, anuncio_id)
    if not anuncio:
        raise HTTPException(status_code=404, detail="Anuncio no encontrado")

    db.delete(anuncio)
    db.commit()
    return None


# --- RUTA PÚBLICA / SUSCRIPTORES ---

@public_router.get("/activos", response_model=List[AnuncioSistemaOut], summary="Obtiene los anuncios globales activos para mostrar en el dashboard")
def get_anuncios_activos_endpoint(db: Session = Depends(get_db)):
    return db.query(AnuncioSistema).filter(AnuncioSistema.activo == True).order_by(AnuncioSistema.creado_en.desc()).all()
