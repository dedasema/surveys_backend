# app/routers/whatsapp_router.py
# --------------------------------
"""
Router FastAPI para integrar Whapi con el flujo de encuestas.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.survey import EntregaEncuesta, PreguntaEncuesta
from app.services import whatsapp_service as ws
from app.services.whatsapp_parser import parse_webhook
from app.services.entregas_service import get_entrega_by_destinatario
from app.services.conversacion_service import (
    iniciar_conversacion_whatsapp,
    procesar_respuesta,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

conversaciones_estado: Dict[str, str] = {}


def _render_multiselect_text(pregunta: PreguntaEncuesta) -> str:
    opciones = "\n".join(f"• {o.texto}" for o in pregunta.opciones)
    return (
        f"{pregunta.texto}\n\n"
        f"Opciones disponibles:\n{opciones}\n\n"
        "Responde escribiendo las opciones que elijas (en cualquier orden)."
    )


async def _send_first_question(db: Session, entrega_id: UUID, chat_id: str) -> None:
    conv = await iniciar_conversacion_whatsapp(db, entrega_id)
    pregunta = db.query(PreguntaEncuesta).get(conv.pregunta_actual_id)
    if not pregunta:
        raise ValueError("No se pudo obtener la primera pregunta")

    if pregunta.tipo_pregunta_id == 3 and pregunta.opciones:  # selección única
        opciones_txt = "\n".join([f"{i+1}. {o.texto}" for i, o in enumerate(pregunta.opciones)])
        msg = f"*{pregunta.texto}*\n\n{opciones_txt}\n\n_Responde con el número o texto de tu opción._"
        res = await ws.send_text(chat_id, msg)
        if not res.get("success"):
            await ws.send_list(chat_id, pregunta.texto, [o.texto for o in pregunta.opciones])

    elif pregunta.tipo_pregunta_id == 4:  # multiselección
        await ws.send_text(chat_id, _render_multiselect_text(pregunta))

    else:  # texto / numérico
        await ws.send_text(chat_id, f"*{pregunta.texto}*")


async def _send_next(db: Session, res: Dict, chat_id: str) -> None:
    tp = res.get("tipo_pregunta")

    if tp == 3 and res.get("opciones"):  # selección única
        opciones_txt = "\n".join([f"{i+1}. {o}" for i, o in enumerate(res["opciones"])])
        msg = f"*{res['siguiente_pregunta']}*\n\n{opciones_txt}\n\n_Responde con el número o texto de tu opción._"
        res_envio = await ws.send_text(chat_id, msg)
        if not res_envio.get("success"):
            await ws.send_list(chat_id, res["siguiente_pregunta"], res["opciones"])

    elif tp == 4:  # multiselección
        opciones = "\n".join(f"• {o}" for o in res["opciones"])
        await ws.send_text(
            chat_id,
            f"*{res['siguiente_pregunta']}*\n\n"
            f"Opciones disponibles:\n{opciones}\n\n"
            "Responde escribiendo las opciones que elijas.",
        )

    else:  # texto / numérico
        await ws.send_text(chat_id, f"*{res['siguiente_pregunta']}*")


@router.get("/webhook")
async def verify_webhook_meta(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """
    Endpoint de verificación exigido por Meta WhatsApp Cloud API.
    """
    verify_token = settings.WHATSAPP_VERIFY_TOKEN or "surveys_whatsapp_verify_token_2026"
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("Webhook de Meta WhatsApp verificado exitosamente.")
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    # ------------------------------------------------ cuerpo + parser
    payload = json.loads((await request.body()).decode())
    data = parse_webhook(payload)

    if data["kind"] in ("status", "own", "non_text", "unknown"):
        return {"success": True, "message": f"Ignored {data['kind']}"}

    if data["kind"] == "error":
        logger.error("Parser error: %s", data["error"])
        return {"success": False, "error": data["error"]}

    numero = data["from_number"]
    texto = data["text"].strip()
    payload_id = data.get("payload_id", "")
    chat_id = f"{numero}@c.us"

    entrega: EntregaEncuesta | None = get_entrega_by_destinatario(db, telefono=numero)
    if not entrega or entrega.estado_id == 3:  # respondido
        await ws.send_text(chat_id, "No tengo encuestas pendientes para este número 😊")
        return {"success": True, "message": "No pending delivery"}

    # Conversación desde PostgreSQL (Persistente ante reinicios)
    conv = entrega.conversacion[0] if entrega.conversacion else None

    # Caso A: Aún no inició la conversación (Esperando confirmación)
    if not conv:
        normalized = texto.lower().replace("í", "i")
        confirmado = normalized in ("si", "yes", "ok", "iniciar", "1") or payload_id == "btn_si"
        rechazado = normalized in ("no", "nop") or payload_id == "btn_no"

        if confirmado:
            await _send_first_question(db, entrega.id, chat_id)
            return {"success": True, "message": "Survey started"}

        if rechazado:
            await ws.send_text(chat_id, "Entendido. Cuando desees empezar escribe INICIAR.")
            return {"success": True, "message": "Survey declined"}

        # Si mandó cualquier otra palabra antes de confirmar
        await ws.send_confirm(
            chat_id,
            "Responde 'Sí' para comenzar la encuesta ahora o 'No' para más tarde.",
        )
        return {"success": True, "message": "Confirmation requested"}

    # Caso B: Encuesta en progreso (Persistente)
    if conv.completada:
        await ws.send_text(chat_id, "¡Ya has completado esta encuesta! Muchas gracias por tus respuestas. 🙏")
        return {"success": True, "message": "Survey already completed"}

    res = await procesar_respuesta(db, conv.id, texto)

    if res.get("retry"):
        await ws.send_text(chat_id, res["mensaje"])
        return {"success": True, "message": "Retry requested"}

    if res.get("completada"):
        mark_as_responded(db, entrega.id)
        await ws.send_text(chat_id, "¡Muchas gracias! Has completado la encuesta exitosamente. 🎉")
        return {"success": True, "message": "Survey completed"}

    await _send_next(db, res, chat_id)
    return {"success": True, "message": "Next question sent"}



@router.get("/webhook")
async def verify_webhook(request: Request):
    if (
        request.query_params.get("hub.mode") == "subscribe"
        and request.query_params.get("hub.verify_token") == settings.WHAPI_TOKEN
    ):
        return Response(content=request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/reset/{numero}")
async def reset_conversation(numero: str):
    chat_id = numero if "@c.us" in numero else f"{numero}@c.us"
    prev = conversaciones_estado.pop(chat_id, None)
    return {"success": True, "prev_state": prev} if prev else {"success": False}


@router.get("/status")
async def get_status():
    resumen: Dict[str, int] = {}
    for st in conversaciones_estado.values():
        resumen[st] = resumen.get(st, 0) + 1
    return {"total": len(conversaciones_estado), "detalle": resumen}


@router.post("/send")
async def manual_send(numero: str, mensaje: str, opciones: List[str] | None = None):
    return (
        await ws.send_list(numero, mensaje, opciones)
        if opciones
        else await ws.send_text(numero, mensaje)
    )
