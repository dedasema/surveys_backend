from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from uuid import UUID
import jwt
from datetime import datetime
from typing import Dict, List

from app.core.database import get_db
from app.core.config import settings
from app.services.shared_service import get_entrega_con_plantilla
from app.services.respuestas_service import create_respuesta
from app.services.entregas_service import mark_as_responded
from app.core.constants import ESTADO_RESPONDIDO
from app.schemas.respuestas_schema import RespuestaCreateEmail, RespuestaEncuestaCreate, RespuestaPreguntaCreate

router = APIRouter(
    prefix="/encuestas",
    tags=["Encuestas Públicas"]
)

@router.get("/verificar/{token}")
async def verificar_token(token: str, db: Session = Depends(get_db)):
    """
    Verifica la validez de un token de encuesta y devuelve los detalles
    de la entrega si es válido
    """
    try:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            entrega_id = UUID(payload["sub"])
        except Exception:
            entrega_id = UUID(token)
        
        # Verificar que la entrega existe y está activa
        entrega = get_entrega_con_plantilla(db, entrega_id)
        if not entrega:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Encuesta no encontrada"
            )
        
        # Verificar que la entrega no haya sido respondida ya
        if entrega.estado_id == ESTADO_RESPONDIDO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta encuesta ya ha sido respondida"
            )
        
        # Devolver los datos necesarios para mostrar la encuesta
        dest_nombre = entrega.destinatario.nombre if entrega.destinatario else "Entrega en Papel"
        dest_email = entrega.destinatario.email if entrega.destinatario else "papel@surveysaas.local"

        return {
            "entrega_id": str(entrega.id),
            "campana": {
                "id": str(entrega.campana.id),
                "nombre": entrega.campana.nombre
            },
            "plantilla": {
                "id": str(entrega.campana.plantilla.id),
                "nombre": entrega.campana.plantilla.nombre,
                "descripcion": entrega.campana.plantilla.descripcion,
                "preguntas": [{
                    "id": str(pregunta.id),
                    "texto": pregunta.texto,
                    "tipo_pregunta_id": pregunta.tipo_pregunta_id,
                    "obligatorio": pregunta.obligatorio,
                    "orden": pregunta.orden,
                    "opciones": [{
                        "id": str(opcion.id),
                        "texto": opcion.texto,
                        "valor": opcion.valor
                    } for opcion in pregunta.opciones] if hasattr(pregunta, 'opciones') else []
                } for pregunta in sorted(entrega.campana.plantilla.preguntas, key=lambda x: x.orden)]
            },
            "destinatario": {
                "nombre": dest_nombre,
                "email": dest_email
            }
        }
        
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token o ID de entrega inválido"
        )

@router.post("/responder/{token}")
async def responder_encuesta(
    token: str, 
    respuestas: List[RespuestaCreateEmail] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Recibe y guarda las respuestas de una encuesta por email
    """
    try:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            entrega_id = UUID(payload["sub"])
        except Exception:
            entrega_id = UUID(token)
        
        # Verificar que la entrega existe y no ha sido respondida
        entrega = get_entrega_con_plantilla(db, entrega_id)
        if not entrega:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Encuesta no encontrada"
            )
            
        if entrega.estado_id == ESTADO_RESPONDIDO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta encuesta ya ha sido respondida"
            )
            
        # Convertir respuestas del formato email al formato esperado por create_respuesta
        respuestas_preguntas = []
        
        for r in respuestas:
            pregunta_id = UUID(r.pregunta_id)
            
            if r.tipo_respuesta == "texto" and r.texto is not None:
                # Para respuestas de texto
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta_id,
                    texto=r.texto,
                    metadatos={}
                )
                respuestas_preguntas.append(respuesta_pregunta)
                
            elif r.tipo_respuesta == "numero" and r.numero is not None:
                # Para respuestas numéricas
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta_id,
                    numero=r.numero,
                    metadatos={}
                )
                respuestas_preguntas.append(respuesta_pregunta)
                
            elif r.tipo_respuesta == "opcion" and r.opcion_id is not None:
                # Para selección única
                respuesta_pregunta = RespuestaPreguntaCreate(
                    pregunta_id=pregunta_id,
                    opcion_id=UUID(r.opcion_id),
                    metadatos={}
                )
                respuestas_preguntas.append(respuesta_pregunta)
                
            elif r.tipo_respuesta == "opciones" and r.opciones_ids:
                # Para selección múltiple - crear una respuesta por cada opción seleccionada
                for opcion_id in r.opciones_ids:
                    respuesta_pregunta = RespuestaPreguntaCreate(
                        pregunta_id=pregunta_id,
                        opcion_id=UUID(opcion_id),
                        metadatos={}
                    )
                    respuestas_preguntas.append(respuesta_pregunta)
        
        respuesta_data = RespuestaEncuestaCreate(
            respuestas_preguntas=respuestas_preguntas
        )
        
        respuesta_encuesta = create_respuesta(db, entrega_id, respuesta_data)
        
        
        entrega_actualizada = get_entrega_con_plantilla(db, entrega_id)
        if entrega_actualizada.estado_id != ESTADO_RESPONDIDO:
            mark_as_responded(db, entrega_id)
        
        return {
            "status": "success",
            "message": "Respuestas guardadas correctamente",
            "respuesta_id": str(respuesta_encuesta.id)
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El enlace de la encuesta ha expirado"
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando las respuestas: {str(e)}"
        )


class InterpretacionVozRequest(BaseModel):
    pregunta_id: UUID
    transcripcion: str


@router.post("/interpretar-voz")
async def interpretar_voz_endpoint(
    payload: InterpretacionVozRequest,
    db: Session = Depends(get_db)
):
    """
    Interpreta con Gemini la transcripción de voz del usuario para una pregunta.
    Devuelve la opción matcheada (opcion_id) o el texto limpio.
    """
    import json
    import re
    from sqlalchemy.orm import joinedload
    from app.models.survey import PreguntaEncuesta
    from app.services.gemini_service import call_gemini_text

    pregunta = db.query(PreguntaEncuesta).options(joinedload(PreguntaEncuesta.opciones)).filter(PreguntaEncuesta.id == payload.pregunta_id).first()
    if not pregunta:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada")

    if pregunta.tipo_pregunta_id in (3, 4) and pregunta.opciones:
        opciones_map = {str(o.id): o.texto for o in pregunta.opciones}
        prompt = (
            f"Dada la pregunta '{pregunta.texto}' y las siguientes opciones válidas:\n"
            f"{json.dumps(opciones_map, ensure_ascii=False)}\n\n"
            f"El usuario respondió por voz: '{payload.transcripcion}'.\n"
            "Identifica cuál opción eligió el usuario. Devuelve ÚNICAMENTE un objeto JSON con la estructura:\n"
            "{\"opcion_id\": \"UUID_ELEGIDO\" o null, \"texto_limpio\": \"TEXTO\"}"
        )
        try:
            raw = await call_gemini_text(prompt, "Responde únicamente JSON válido.")
            cleaned = re.sub(r"^```json\s*", "", raw.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
            return json.loads(cleaned)
        except Exception:
            for op in pregunta.opciones:
                if op.texto.lower() in payload.transcripcion.lower():
                    return {"opcion_id": str(op.id), "texto_limpio": op.texto}
            return {"opcion_id": None, "texto_limpio": payload.transcripcion}

    return {"opcion_id": None, "texto_limpio": payload.transcripcion}