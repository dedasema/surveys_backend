"""
FastAPI Routers for Respuestas and Public Surveys.
"""

from typing import List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
import jwt

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.core.constants import ESTADO_RESPONDIDO
from app.schemas.auth import TokenData
from app.schemas.respuestas_schema import (
    RespuestaEncuestaCreate,
    RespuestaEncuestaUpdate,
    RespuestaEncuestaOut,
    RespuestaCreateEmail,
)
from app.services.entregas_service import get_entrega, mark_as_responded
from app.services.shared_service import get_entrega_con_plantilla
from app.services.respuestas_service import (
    create_respuesta,
    get_respuesta,
    list_respuestas_by_entrega,
    update_respuesta,
    delete_respuesta,
    registrar_respuestas_publicas,
)

respuestas_public_router = APIRouter(
    prefix="/public/entregas/{entrega_id}/respuestas",
    tags=["Respuestas Públicas"],
)

respuestas_private_router = APIRouter(
    prefix="/campanas/{campana_id}/entregas/{entrega_id}/respuestas",
    tags=["Respuestas Admin"],
)

encuestas_public_router = APIRouter(
    prefix="/encuestas",
    tags=["Encuestas Públicas"],
)


# ────────── Respuestas Públicas ──────────

@respuestas_public_router.post("", response_model=RespuestaEncuestaOut, status_code=status.HTTP_201_CREATED)
async def submit_respuesta_endpoint(
    entrega_id: UUID,
    payload: RespuestaEncuestaCreate,
    db: Session = Depends(get_db),
):
    entrega = get_entrega(db, entrega_id)
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    if entrega.respondido_en:
        raise HTTPException(status_code=400, detail="Esta encuesta ya ha sido respondida")
    if payload.consentimiento_aceptado is not True:
        raise HTTPException(status_code=400, detail="Debe aceptar el consentimiento informado para enviar las respuestas.")

    from datetime import datetime, timezone
    entrega.consentimiento_aceptado = True
    entrega.consentimiento_en = datetime.now(timezone.utc)
    db.add(entrega)
    db.commit()
    return create_respuesta(db, entrega_id, payload)


@respuestas_public_router.get("/{respuesta_id}", response_model=RespuestaEncuestaOut)
async def view_respuesta_endpoint(
    entrega_id: UUID,
    respuesta_id: UUID,
    db: Session = Depends(get_db),
):
    respuesta = get_respuesta(db, respuesta_id)
    if not respuesta or respuesta.entrega_id != entrega_id:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    return respuesta


# ────────── Respuestas Admin ──────────

@respuestas_private_router.post("", response_model=RespuestaEncuestaOut, status_code=status.HTTP_201_CREATED)
async def create_respuesta_admin_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    payload: RespuestaEncuestaCreate,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada en esta campaña")
    return create_respuesta(db, entrega_id, payload)


@respuestas_private_router.get("", response_model=List[RespuestaEncuestaOut])
async def list_respuestas_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(status_code=404, detail="Entrega no encontrada en esta campaña")
    return list_respuestas_by_entrega(db, entrega_id)


# ────────── Verificación y Envío de Encuestas Públicas ──────────

@encuestas_public_router.get("/verificar/{token}")
async def verificar_token_endpoint(token: str, db: Session = Depends(get_db)):
    try:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            entrega_id = UUID(payload["sub"])
        except Exception:
            entrega_id = UUID(token)

        entrega = get_entrega_con_plantilla(db, entrega_id)
        if not entrega:
            raise HTTPException(status_code=404, detail="Encuesta no encontrada")
        if entrega.estado_id == ESTADO_RESPONDIDO:
            raise HTTPException(status_code=400, detail="Esta encuesta ya ha sido respondida")

        dest_nombre = entrega.destinatario.nombre if entrega.destinatario else "Entrega en Papel"
        dest_email = entrega.destinatario.email if entrega.destinatario else "papel@surveysaas.local"

        return {
            "entrega_id": str(entrega.id),
            "campana": {
                "id": str(entrega.campana.id),
                "nombre": entrega.campana.nombre,
            },
            "plantilla": {
                "id": str(entrega.campana.plantilla.id),
                "nombre": entrega.campana.plantilla.nombre,
                "descripcion": entrega.campana.plantilla.descripcion,
                "preguntas": [
                    {
                        "id": str(p.id),
                        "texto": p.texto,
                        "tipo_pregunta_id": p.tipo_pregunta_id,
                        "obligatorio": p.obligatorio,
                        "orden": p.orden,
                        "opciones": [
                            {"id": str(o.id), "texto": o.texto, "valor": o.valor}
                            for o in p.opciones
                        ],
                    }
                    for p in entrega.campana.plantilla.preguntas
                ],
            },
            "destinatario": {
                "nombre": dest_nombre,
                "email": dest_email,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token inválido: {str(e)}")


@encuestas_public_router.post("/responder/{token}", status_code=status.HTTP_201_CREATED)
async def responder_encuesta_email_endpoint(
    token: str,
    payload: RespuestaCreateEmail,
    db: Session = Depends(get_db),
):
    try:
        try:
            jwt_data = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            entrega_id = UUID(jwt_data["sub"])
        except Exception:
            entrega_id = UUID(token)

        return registrar_respuestas_publicas(db, entrega_id, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error procesando la respuesta: {str(e)}")
