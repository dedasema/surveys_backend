"""
FastAPI Routers for Respuestas and Public Surveys.
"""

from datetime import datetime, timezone
from typing import List, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Body, Header, Query
from sqlalchemy.orm import Session
import jwt

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.core.constants import ESTADO_RESPONDIDO
from app.models.survey import EntregaEncuesta
from app.schemas.auth import TokenData
from app.schemas.respuestas_schema import (
    RespuestaEncuestaCreate,
    RespuestaEncuestaOut,
)
from app.services.entregas_service import get_entrega
from app.services.shared_service import get_entrega_con_plantilla
from app.services.respuestas_service import (
    create_respuesta,
    get_respuesta,
    list_respuestas_by_entrega,
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


@encuestas_public_router.post("/responder/{token}", status_code=status.HTTP_200_OK)
async def responder_encuesta_email_endpoint(
    token: str,
    payload: Any = Body(...),
    consentimiento_aceptado: bool = Query(
        True,
        description="Confirmación de consentimiento informado del encuestado",
    ),
    x_consentimiento_aceptado: Optional[str] = Header(
        None,
        alias="X-Consentimiento-Aceptado",
        description="Header alternativo para consentimiento informado",
    ),
    db: Session = Depends(get_db),
):
    try:
        try:
            jwt_data = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            entrega_id = UUID(jwt_data["sub"])
        except Exception:
            entrega_id = UUID(token)

        # Resolver consentimiento informado (prioridad al header si se especifica)
        consentimiento_final = consentimiento_aceptado
        if x_consentimiento_aceptado is not None:
            consentimiento_final = x_consentimiento_aceptado.strip().lower() in (
                "true", "1", "yes", "si"
            )

        # Normalizar payload
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            if "respuestas_preguntas" in payload:
                items = payload["respuestas_preguntas"]
            elif "respuestas" in payload:
                items = payload["respuestas"]
            else:
                items = [payload]
        else:
            items = [payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()]

        normalized_items = []
        for it in items:
            if hasattr(it, "model_dump"):
                normalized_items.append(it.model_dump())
            elif hasattr(it, "dict"):
                normalized_items.append(it.dict())
            elif isinstance(it, dict):
                normalized_items.append(it)

        # Registrar respuestas
        resp = await registrar_respuestas_publicas(
            db,
            entrega_id,
            {"respuestas_preguntas": normalized_items},
        )

        # Guardar confirmación y marca temporal del consentimiento informado
        entrega = (
            db.get(EntregaEncuesta, entrega_id)
            if hasattr(db, "get")
            else db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega_id).first()
        )
        if entrega:
            entrega.consentimiento_aceptado = bool(consentimiento_final)
            entrega.consentimiento_en = datetime.now(timezone.utc)
            db.commit()
            db.refresh(entrega)

        return {
            "status": "success",
            "message": "Respuestas guardadas correctamente",
            "respuesta_id": str(resp.id),
            "consentimiento_aceptado": bool(consentimiento_final),
            "consentimiento_en": (
                entrega.consentimiento_en.isoformat()
                if entrega and entrega.consentimiento_en
                else None
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error procesando la respuesta: {str(e)}")
