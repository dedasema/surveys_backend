# app/routers/encuestas_adaptativas_router.py
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.database import get_db
from app.core.constants import ESTADO_RESPONDIDO
from app.models.survey import (
    EntregaEncuesta, PreguntaEncuesta, ConversacionEncuesta,
    RespuestaTemp, RespuestaEncuesta, RespuestaPregunta, PlantillaEncuesta
)
from app.models.audio_respuesta import AudioRespuesta
from app.models.regla_ramificacion import ReglaRamificacion
from app.services.ramificacion_service import (
    seleccionar_siguiente_pregunta_adaptativa,
    detectar_sentimiento_o_baja_calificacion,
    generar_pregunta_seguimiento
)
from app.services.hash_chain_service import vincular_hash_cadena

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/encuestas/adaptativa", tags=["Encuestas Adaptativas (RF17, RF17b)"])

# ────────── Esquemas Pydantic ──────────

class RespuestaAdaptativaInput(BaseModel):
    pregunta_id: Optional[UUID] = None
    texto: Optional[str] = None
    numero: Optional[float] = None
    opcion_id: Optional[UUID] = None
    audio_respuesta_id: Optional[UUID] = None

class ReglaRamificacionCreate(BaseModel):
    pregunta_origen_id: UUID
    condicion_semantica: str
    pregunta_destino_id: Optional[UUID] = None
    es_fin_encuesta: bool = False
    orden_prioridad: int = 1

# ────────── Endpoints de Flujo Adaptativo ──────────

@router.post("/{entrega_id}/iniciar", summary="Iniciar o reanudar sesión de encuesta adaptativa (RF17)")
async def iniciar_encuesta_adaptativa(entrega_id: UUID, db: Session = Depends(get_db)):
    entrega = db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega_id).first()
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")

    if entrega.estado_id == ESTADO_RESPONDIDO or entrega.respondido_en is not None:
        return {
            "fin_encuesta": True,
            "mensaje": "La encuesta ya ha sido completada.",
            "siguiente_pregunta": None
        }

    plantilla = entrega.campana.plantilla
    if not plantilla:
        raise HTTPException(status_code=400, detail="La campaña no tiene una plantilla asociada")

    conversacion = db.query(ConversacionEncuesta).filter_by(entrega_id=entrega_id).first()
    if not conversacion:
        conversacion = ConversacionEncuesta(
            entrega_id=entrega_id,
            historial=[],
            preguntas_generativas_usadas=0,
            completada=False
        )
        db.add(conversacion)
        db.flush()

    if conversacion.completada:
        return {
            "fin_encuesta": True,
            "mensaje": "La encuesta ya ha sido completada.",
            "siguiente_pregunta": None
        }

    # Si hay una pregunta generativa activa pendiente de responder
    if conversacion.pregunta_generativa_activa:
        return {
            "fin_encuesta": False,
            "es_generativa": True,
            "siguiente_pregunta": {
                "id": None,
                "texto": conversacion.pregunta_generativa_activa,
                "tipo_pregunta_id": 1,
                "obligatorio": False,
                "opciones": []
            },
            "justificacion": "Pregunta generativa de seguimiento pendiente"
        }

    # Si ya tiene una pregunta actual asignada
    if conversacion.pregunta_actual_id:
        p_actual = db.query(PreguntaEncuesta).filter_by(id=conversacion.pregunta_actual_id).first()
        if p_actual:
            return {
                "fin_encuesta": False,
                "es_generativa": False,
                "siguiente_pregunta": {
                    "id": str(p_actual.id),
                    "texto": p_actual.texto,
                    "tipo_pregunta_id": p_actual.tipo_pregunta_id,
                    "obligatorio": p_actual.obligatorio,
                    "opciones": [{"id": str(o.id), "texto": o.texto, "valor": o.valor} for o in p_actual.opciones]
                },
                "justificacion": "Reanudación en pregunta actual"
            }

    # Primera pregunta del banco de la plantilla (orden ASC)
    primera_pregunta = (
        db.query(PreguntaEncuesta)
        .filter_by(plantilla_id=plantilla.id)
        .order_by(PreguntaEncuesta.orden.asc())
        .first()
    )
    if not primera_pregunta:
        return {
            "fin_encuesta": True,
            "mensaje": "La plantilla no tiene preguntas disponibles.",
            "siguiente_pregunta": None
        }

    conversacion.pregunta_actual_id = primera_pregunta.id
    db.commit()

    return {
        "fin_encuesta": False,
        "es_generativa": False,
        "siguiente_pregunta": {
            "id": str(primera_pregunta.id),
            "texto": primera_pregunta.texto,
            "tipo_pregunta_id": primera_pregunta.tipo_pregunta_id,
            "obligatorio": primera_pregunta.obligatorio,
            "opciones": [{"id": str(o.id), "texto": o.texto, "valor": o.valor} for o in primera_pregunta.opciones]
        },
        "justificacion": "Inicio con primera pregunta del banco"
    }

@router.post("/{entrega_id}/responder", summary="Responder y avanzar adaptativamente (RF17, RF17b)")
async def responder_adaptativo(
    entrega_id: UUID,
    payload: RespuestaAdaptativaInput,
    db: Session = Depends(get_db)
):
    entrega = db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega_id).first()
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")

    conversacion = db.query(ConversacionEncuesta).filter_by(entrega_id=entrega_id).first()
    if not conversacion:
        raise HTTPException(status_code=400, detail="Debe iniciar la encuesta antes de responder")

    if conversacion.completada or entrega.estado_id == ESTADO_RESPONDIDO:
        return {
            "fin_encuesta": True,
            "mensaje": "La encuesta ya fue finalizada.",
            "siguiente_pregunta": None
        }

    # Si se adjuntó un ID de audio transcripto (RF18) y no hay texto manual
    if payload.audio_respuesta_id and not payload.texto:
        audio_rec = db.query(AudioRespuesta).filter_by(id=payload.audio_respuesta_id).first()
        if audio_rec and audio_rec.transcripcion_texto:
            payload.texto = audio_rec.transcripcion_texto

    texto_respuesta = payload.texto or ""
    numero_respuesta = payload.numero

    # Identificar la pregunta que se está respondiendo
    es_respuesta_a_generativa = bool(conversacion.pregunta_generativa_activa)
    pregunta_texto = conversacion.pregunta_generativa_activa

    if not es_respuesta_a_generativa:
        pid = payload.pregunta_id or conversacion.pregunta_actual_id
        if pid:
            p_obj = db.query(PreguntaEncuesta).filter_by(id=pid).first()
            if p_obj:
                pregunta_texto = p_obj.texto
                # Guardar respuesta temporal
                resp_temp = RespuestaTemp(
                    entrega_id=entrega.id,
                    pregunta_id=p_obj.id,
                    texto=texto_respuesta,
                    numero=numero_respuesta,
                    opcion_id=payload.opcion_id
                )
                db.add(resp_temp)

    # Actualizar historial de la conversación
    historial = list(conversacion.historial or [])
    historial.append({
        "pregunta_id": str(payload.pregunta_id or conversacion.pregunta_actual_id) if not es_respuesta_a_generativa else None,
        "pregunta": pregunta_texto or "Pregunta",
        "respuesta": texto_respuesta or (str(numero_respuesta) if numero_respuesta is not None else ""),
        "es_generativa": es_respuesta_a_generativa
    })
    conversacion.historial = historial

    plantilla = entrega.campana.plantilla
    plantilla_id = plantilla.id if plantilla else None

    # Lógica de pregunta generativa vs banco adaptativo
    if es_respuesta_a_generativa:
        # El encuestado acaba de responder la pregunta de seguimiento generativa
        conversacion.pregunta_generativa_activa = None
        # Continuar con el banco adaptativo
        respondidas_ids = [
            h["pregunta_id"] for h in historial if h.get("pregunta_id")
        ]
        decision = await seleccionar_siguiente_pregunta_adaptativa(
            db=db,
            plantilla_id=plantilla_id,
            pregunta_actual_id=conversacion.pregunta_actual_id,
            respuesta_actual_texto=texto_respuesta,
            historial=historial,
            preguntas_respondidas_ids=respondidas_ids
        )
    else:
        # Verificar si corresponde disparar pregunta generativa empática (RF17b)
        es_negativo = detectar_sentimiento_o_baja_calificacion(texto_respuesta, numero_respuesta)
        if es_negativo and conversacion.preguntas_generativas_usadas < 1:
            desc_plantilla = plantilla.descripcion or plantilla.nombre if plantilla else "Satisfacción de servicio"
            pregunta_gen = await generar_pregunta_seguimiento(
                contexto_encuesta=desc_plantilla,
                respuesta_negativa=texto_respuesta or f"Calificación baja: {numero_respuesta}"
            )
            conversacion.preguntas_generativas_usadas += 1
            conversacion.pregunta_generativa_activa = pregunta_gen
            db.commit()

            return {
                "fin_encuesta": False,
                "es_generativa": True,
                "siguiente_pregunta": {
                    "id": None,
                    "texto": pregunta_gen,
                    "tipo_pregunta_id": 1,
                    "obligatorio": False,
                    "opciones": []
                },
                "justificacion": "Pregunta de seguimiento generativa activada por insatisfacción o calificación baja (RF17b)"
            }

        # Selección normal desde el banco de candidatas (RF17)
        respondidas_ids = [
            h["pregunta_id"] for h in historial if h.get("pregunta_id")
        ]
        decision = await seleccionar_siguiente_pregunta_adaptativa(
            db=db,
            plantilla_id=plantilla_id,
            pregunta_actual_id=conversacion.pregunta_actual_id,
            respuesta_actual_texto=texto_respuesta,
            historial=historial,
            preguntas_respondidas_ids=respondidas_ids
        )

    # Procesar decisión (Fin de encuesta vs siguiente pregunta del banco)
    if decision.get("fin_encuesta") or not decision.get("siguiente_pregunta_id"):
        # Marcar conversación y entrega como completadas
        conversacion.completada = True
        conversacion.pregunta_actual_id = None
        entrega.estado_id = ESTADO_RESPONDIDO
        entrega.respondido_en = func.now()

        # Consolidar respuestas temporales en RespuestaEncuesta y vincular Hash-Chain (RNF8)
        respuestas_temporales = db.query(RespuestaTemp).filter_by(entrega_id=entrega.id).all()
        numeros = [float(r.numero) for r in respuestas_temporales if r.numero is not None]
        promedio = (sum(numeros) / len(numeros)) if numeros else None

        raw_payload = {
            "entrega_id": str(entrega.id),
            "historial": conversacion.historial,
            "respuestas": [
                {
                    "pregunta_id": str(r.pregunta_id),
                    "texto": r.texto,
                    "numero": float(r.numero) if r.numero is not None else None
                }
                for r in respuestas_temporales
            ]
        }

        nueva_respuesta = RespuestaEncuesta(
            entrega_id=entrega.id,
            puntuacion=promedio,
            raw_payload=raw_payload
        )
        db.add(nueva_respuesta)
        db.flush()

        for rt in respuestas_temporales:
            rp = RespuestaPregunta(
                respuesta_id=nueva_respuesta.id,
                pregunta_id=rt.pregunta_id,
                texto=rt.texto,
                numero=rt.numero,
                opcion_id=rt.opcion_id
            )
            db.add(rp)

        # Criptografía: vincular a la cadena de hashes
        vincular_hash_cadena(db, nueva_respuesta, campana_id=entrega.campana_id)
        db.commit()

        # Emitir evento en tiempo real vía WebSocket (RF24)
        try:
            from app.services.websocket_manager import ws_manager
            await ws_manager.broadcast(
                "nueva_respuesta",
                {
                    "respuesta_id": str(nueva_respuesta.id),
                    "entrega_id": str(entrega.id),
                    "puntuacion": float(promedio) if promedio is not None else None,
                    "hash": nueva_respuesta.hash
                },
                campana_id=str(entrega.campana_id)
            )
        except Exception as e_ws:
            logger.warning("No se pudo emitir evento WebSocket nueva_respuesta: %s", e_ws)

        return {
            "fin_encuesta": True,
            "es_generativa": False,
            "siguiente_pregunta": None,
            "justificacion": decision.get("justificacion", "Encuesta finalizada"),
            "hash_integridad": nueva_respuesta.hash
        }

    # Siguiente pregunta del banco
    next_id = UUID(str(decision["siguiente_pregunta_id"]))
    siguiente_p = db.query(PreguntaEncuesta).filter_by(id=next_id).first()
    if not siguiente_p:
        # Fallback si no se encontró
        conversacion.completada = True
        db.commit()
        return {
            "fin_encuesta": True,
            "es_generativa": False,
            "siguiente_pregunta": None,
            "justificacion": "No se encontró la siguiente pregunta en el banco"
        }

    conversacion.pregunta_actual_id = siguiente_p.id
    db.commit()

    return {
        "fin_encuesta": False,
        "es_generativa": False,
        "siguiente_pregunta": {
            "id": str(siguiente_p.id),
            "texto": siguiente_p.texto,
            "tipo_pregunta_id": siguiente_p.tipo_pregunta_id,
            "obligatorio": siguiente_p.obligatorio,
            "opciones": [{"id": str(o.id), "texto": o.texto, "valor": o.valor} for o in siguiente_p.opciones]
        },
        "justificacion": decision.get("justificacion", "Pregunta seleccionada del banco")
    }

@router.get("/{entrega_id}/estado", summary="Consultar estado de la encuesta adaptativa")
async def consultar_estado_adaptativo(entrega_id: UUID, db: Session = Depends(get_db)):
    entrega = db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega_id).first()
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")

    conversacion = db.query(ConversacionEncuesta).filter_by(entrega_id=entrega_id).first()
    return {
        "entrega_id": str(entrega_id),
        "completada": conversacion.completada if conversacion else False,
        "preguntas_generativas_usadas": conversacion.preguntas_generativas_usadas if conversacion else 0,
        "pregunta_actual_id": str(conversacion.pregunta_actual_id) if conversacion and conversacion.pregunta_actual_id else None,
        "total_interacciones": len(conversacion.historial) if conversacion and conversacion.historial else 0
    }

# ────────── CRUD de Reglas de Ramificación Determinísticas ──────────

@router.post("/plantillas/{plantilla_id}/reglas", status_code=status.HTTP_201_CREATED, summary="Crear regla de ramificación")
async def crear_regla_ramificacion(
    plantilla_id: UUID,
    payload: ReglaRamificacionCreate,
    db: Session = Depends(get_db)
):
    plantilla = db.query(PlantillaEncuesta).filter_by(id=plantilla_id).first()
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")

    regla = ReglaRamificacion(
        plantilla_id=plantilla_id,
        pregunta_origen_id=payload.pregunta_origen_id,
        condicion_semantica=payload.condicion_semantica,
        pregunta_destino_id=payload.pregunta_destino_id,
        es_fin_encuesta=payload.es_fin_encuesta,
        orden_prioridad=payload.orden_prioridad
    )
    db.add(regla)
    db.commit()
    db.refresh(regla)
    return {
        "id": str(regla.id),
        "plantilla_id": str(regla.plantilla_id),
        "pregunta_origen_id": str(regla.pregunta_origen_id),
        "condicion_semantica": regla.condicion_semantica,
        "pregunta_destino_id": str(regla.pregunta_destino_id) if regla.pregunta_destino_id else None,
        "es_fin_encuesta": regla.es_fin_encuesta,
        "orden_prioridad": regla.orden_prioridad
    }

@router.get("/plantillas/{plantilla_id}/reglas", summary="Listar reglas de ramificación de una plantilla")
async def listar_reglas_ramificacion(plantilla_id: UUID, db: Session = Depends(get_db)):
    reglas = (
        db.query(ReglaRamificacion)
        .filter_by(plantilla_id=plantilla_id)
        .order_by(ReglaRamificacion.orden_prioridad.asc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "plantilla_id": str(r.plantilla_id),
            "pregunta_origen_id": str(r.pregunta_origen_id),
            "condicion_semantica": r.condicion_semantica,
            "pregunta_destino_id": str(r.pregunta_destino_id) if r.pregunta_destino_id else None,
            "es_fin_encuesta": r.es_fin_encuesta,
            "orden_prioridad": r.orden_prioridad
        }
        for r in reglas
    ]
