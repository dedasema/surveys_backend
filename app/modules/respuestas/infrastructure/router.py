"""
FastAPI Routers for Respuestas and Public Surveys.
"""

from datetime import datetime, timezone
from typing import List, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Body, Header, Query
from sqlalchemy.orm import Session, joinedload
import jwt

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, validate_subscriber_access
from app.core.constants import ESTADO_RESPONDIDO
from app.models.survey import (
    EntregaEncuesta,
    CampanaEncuesta,
    RespuestaEncuesta,
    PreguntaEncuesta,
    OpcionEncuesta,
)
from app.models.cuenta_usuario import CuentaUsuario
from app.schemas.auth import TokenData
from app.schemas.respuestas_schema import (
    RespuestaEncuestaCreate,
    RespuestaEncuestaOut,
    RespuestaListItemOut,
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

respuestas_router = APIRouter(
    prefix="/respuestas",
    tags=["Respuestas"],
)


def _resolve_suscriptor_id(token_data: TokenData, db: Session) -> Optional[UUID]:
    if token_data.role == "admin":
        return None
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


@respuestas_router.get("", response_model=List[RespuestaListItemOut])
async def list_all_respuestas_endpoint(
    campana_id: Optional[UUID] = Query(None, description="Filtrar por ID de campaña"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suscriptor_id = _resolve_suscriptor_id(token_data, db)

    if campana_id:
        campana = db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()
        if not campana:
            raise HTTPException(status_code=404, detail="Campaña no encontrada")
        if not await validate_subscriber_access(token_data, campana.suscriptor_id, db):
            raise HTTPException(status_code=403, detail="No tiene permisos sobre esta campaña")

    query = (
        db.query(RespuestaEncuesta)
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
        .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
        .options(
            joinedload(RespuestaEncuesta.entrega).joinedload(EntregaEncuesta.destinatario),
            joinedload(RespuestaEncuesta.entrega).joinedload(EntregaEncuesta.campana),
            joinedload(RespuestaEncuesta.respuestas_preguntas),
        )
    )

    if campana_id:
        query = query.filter(EntregaEncuesta.campana_id == campana_id)
    elif suscriptor_id:
        query = query.filter(CampanaEncuesta.suscriptor_id == suscriptor_id)

    respuestas = (
        query.order_by(RespuestaEncuesta.recibido_en.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    all_pregunta_ids = set()
    all_opcion_ids = set()
    for r in respuestas:
        for rp in r.respuestas_preguntas:
            if rp.pregunta_id:
                all_pregunta_ids.add(rp.pregunta_id)
            if rp.opcion_id:
                all_opcion_ids.add(rp.opcion_id)

    preguntas_map = {}
    if all_pregunta_ids:
        pregs = db.query(PreguntaEncuesta).filter(PreguntaEncuesta.id.in_(all_pregunta_ids)).all()
        for p in pregs:
            preguntas_map[p.id] = {
                "texto": p.texto,
                "tipo_pregunta_id": p.tipo_pregunta_id,
            }

    opciones_map = {}
    if all_opcion_ids:
        ops = db.query(OpcionEncuesta).filter(OpcionEncuesta.id.in_(all_opcion_ids)).all()
        for o in ops:
            opciones_map[o.id] = o.texto

    results = []
    for r in respuestas:
        detalles = []
        for rp in r.respuestas_preguntas:
            valor = ""
            if rp.opcion_id and rp.opcion_id in opciones_map:
                valor = opciones_map[rp.opcion_id]
            elif rp.texto:
                valor = rp.texto
            elif rp.numero is not None:
                valor = str(rp.numero)

            p_info = preguntas_map.get(rp.pregunta_id, {})
            p_texto = p_info.get("texto", "Pregunta")
            p_tipo = p_info.get("tipo_pregunta_id")

            detalles.append({
                "pregunta_id": rp.pregunta_id,
                "pregunta": p_texto,
                "tipo_pregunta_id": p_tipo,
                "valor": valor,
                "respuesta": valor,
                "numero": float(rp.numero) if rp.numero is not None else None,
                "opcion_id": rp.opcion_id,
                "metadatos": rp.metadatos or {},
            })

        dest_obj = None
        if r.entrega and r.entrega.destinatario:
            dest_obj = {
                "id": r.entrega.destinatario.id,
                "nombre": r.entrega.destinatario.nombre,
                "email": r.entrega.destinatario.email,
                "telefono": r.entrega.destinatario.telefono,
            }
        else:
            dest_obj = {
                "id": None,
                "nombre": "Participante Anónimo",
                "email": None,
                "telefono": None,
            }

        campana_obj = r.entrega.campana if r.entrega else None
        campana_id_val = (
            campana_obj.id if campana_obj else (r.entrega.campana_id if r.entrega else None)
        )
        results.append({
            "id": r.id,
            "entrega_id": r.entrega_id,
            "campana_id": campana_id_val,
            "campana_nombre": campana_obj.nombre if campana_obj else "",
            "creado_en": r.recibido_en,
            "fecha": r.recibido_en,
            "destinatario": dest_obj,
            "detalles": detalles,
            "respuestas": detalles,
            "puntuacion": float(r.puntuacion) if r.puntuacion is not None else None,
            "raw_payload": r.raw_payload or {},
        })

    return results


@respuestas_router.get("/{respuesta_id}", response_model=RespuestaListItemOut)
async def get_single_respuesta_endpoint(
    respuesta_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = (
        db.query(RespuestaEncuesta)
        .options(
            joinedload(RespuestaEncuesta.entrega).joinedload(EntregaEncuesta.destinatario),
            joinedload(RespuestaEncuesta.entrega).joinedload(EntregaEncuesta.campana),
            joinedload(RespuestaEncuesta.respuestas_preguntas),
        )
        .filter(RespuestaEncuesta.id == respuesta_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")

    campana_obj = r.entrega.campana if r.entrega else None
    if campana_obj:
        if not await validate_subscriber_access(token_data, campana_obj.suscriptor_id, db):
            raise HTTPException(status_code=403, detail="No tiene permisos sobre esta respuesta")

    all_pregunta_ids = {rp.pregunta_id for rp in r.respuestas_preguntas if rp.pregunta_id}
    all_opcion_ids = {rp.opcion_id for rp in r.respuestas_preguntas if rp.opcion_id}

    preguntas_map = {}
    if all_pregunta_ids:
        pregs = db.query(PreguntaEncuesta).filter(PreguntaEncuesta.id.in_(all_pregunta_ids)).all()
        for p in pregs:
            preguntas_map[p.id] = {"texto": p.texto, "tipo_pregunta_id": p.tipo_pregunta_id}

    opciones_map = {}
    if all_opcion_ids:
        ops = db.query(OpcionEncuesta).filter(OpcionEncuesta.id.in_(all_opcion_ids)).all()
        for o in ops:
            opciones_map[o.id] = o.texto

    detalles = []
    for rp in r.respuestas_preguntas:
        valor = ""
        if rp.opcion_id and rp.opcion_id in opciones_map:
            valor = opciones_map[rp.opcion_id]
        elif rp.texto:
            valor = rp.texto
        elif rp.numero is not None:
            valor = str(rp.numero)

        p_info = preguntas_map.get(rp.pregunta_id, {})
        detalles.append({
            "pregunta_id": rp.pregunta_id,
            "pregunta": p_info.get("texto", "Pregunta"),
            "tipo_pregunta_id": p_info.get("tipo_pregunta_id"),
            "valor": valor,
            "respuesta": valor,
            "numero": float(rp.numero) if rp.numero is not None else None,
            "opcion_id": rp.opcion_id,
            "metadatos": rp.metadatos or {},
        })

    dest_obj = None
    if r.entrega and r.entrega.destinatario:
        dest_obj = {
            "id": r.entrega.destinatario.id,
            "nombre": r.entrega.destinatario.nombre,
            "email": r.entrega.destinatario.email,
            "telefono": r.entrega.destinatario.telefono,
        }
    else:
        dest_obj = {
            "id": None,
            "nombre": "Participante Anónimo",
            "email": None,
            "telefono": None,
        }

    return {
        "id": r.id,
        "entrega_id": r.entrega_id,
        "campana_id": campana_obj.id if campana_obj else None,
        "campana_nombre": campana_obj.nombre if campana_obj else "",
        "creado_en": r.recibido_en,
        "fecha": r.recibido_en,
        "destinatario": dest_obj,
        "detalles": detalles,
        "respuestas": detalles,
        "puntuacion": float(r.puntuacion) if r.puntuacion is not None else None,
        "raw_payload": r.raw_payload or {},
    }


# ────────── Respuestas Públicas ──────────

@respuestas_public_router.post(
    "",
    response_model=RespuestaEncuestaOut,
    status_code=status.HTTP_201_CREATED,
)
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
        raise HTTPException(
            status_code=400,
            detail="Debe aceptar el consentimiento informado para enviar las respuestas.",
        )

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

@respuestas_private_router.post(
    "",
    response_model=RespuestaEncuestaOut,
    status_code=status.HTTP_201_CREATED,
)
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
        dest_email = (
            entrega.destinatario.email if entrega.destinatario else "papel@surveysaas.local"
        )

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
