# app/services/conversacion_service.py
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)

_client = None

def get_openai_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client

# --------------------------------------------------------------------------- #
# UTILIDADES
# --------------------------------------------------------------------------- #


def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt.lower().strip())


# --------------------------------------------------------------------------- #
# GPT PROMPT BUILDER
# --------------------------------------------------------------------------- #


def _build_prompt(respuesta: str, opciones: List[str], multiple: bool) -> List[Dict]:
    lista = "\n".join(f"{i}. {op}" for i, op in enumerate(opciones, 1))
    system = (
        "Eres un parser JSON. Devuelve exclusivamente un JSON con las claves "
        '"indices" (lista de enteros base-0) y "confidence" (0-1). '
        "Si no estás seguro, deja indices=[] y confidence=0."
    )
    user = (
        f"Opciones posibles:\n{lista}\n\n"
        f"Mensaje del usuario:\n\"{respuesta}\"\n\n"
        f"{'Puede haber varias opciones.' if multiple else 'Sólo una opción.'}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------- #
# DESAMBIGUAR OPCIONES
# --------------------------------------------------------------------------- #


async def _match_opcion_ai(
    respuesta: str,
    opciones: List[str],
    multiple: bool,
) -> Tuple[Any | None, str | None]:
    if not multiple:
        plain = _norm(respuesta)
        for i, op in enumerate(opciones):
            if plain == _norm(op):
                return i, None
        for n in re.findall(r"\b\d+\b", respuesta):
            idx = int(n) - 1
            if 0 <= idx < len(opciones):
                return idx, None

    try:
        client = get_openai_client()
        chat = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=_build_prompt(respuesta, opciones, multiple),
            temperature=0.0,
            timeout=8,
        )
        raw = chat.choices[0].message.content.strip()
        data = json.loads(raw)
        idxs = data.get("indices", [])
        conf = float(data.get("confidence", 0))

        if idxs and conf >= 0.5:
            if multiple:
                idxs = [i for i in idxs if 0 <= i < len(opciones)]
                return (idxs, None) if idxs else (None, "No reconocí las opciones.")
            else:
                i = idxs[0]
                return (i, None) if 0 <= i < len(opciones) else (
                    None,
                    "No reconocí la opción.",
                )
    except Exception as exc:
        logger.warning("GPT falló: %s", exc)

    texto = (
        "No entendí tu elección 🤔.\n"
        "Por favor escribe nuevamente "
        f"{'una o varias' if multiple else 'una'} de las siguientes opciones:\n"
        + "\n".join(f"- {op}" for op in opciones)
    )
    return None, texto


# --------------------------------------------------------------------------- #
# FUNCIÓN PRINCIPAL
# --------------------------------------------------------------------------- #


async def procesar_respuesta(
    db: Session,
    conversacion_id: UUID,
    respuesta: str,
) -> Dict[str, Any]:
    conv = (
        db.query(ConversacionEncuesta)
        .options(
            joinedload(ConversacionEncuesta.entrega)
            .joinedload(EntregaEncuesta.campana)
            .joinedload(CampanaEncuesta.plantilla)
        )
        .filter(ConversacionEncuesta.id == conversacion_id)
        .first()
    )
    if not conv:
        raise ValueError("Conversación no encontrada")
    if conv.completada:
        return {"completada": True}

    conv.historial = conv.historial or []
    conv.historial.append(
        {"role": "user", "content": respuesta, "timestamp": datetime.now().isoformat()}
    )

    pregunta = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.id == conv.pregunta_actual_id)
        .first()
    )
    if not pregunta:
        raise ValueError("Pregunta actual no encontrada")

    # -------- Validación -------------------------------------------------- #
    if pregunta.tipo_pregunta_id == 1:
        valor = respuesta
    elif pregunta.tipo_pregunta_id == 2:
        try:
            valor = float(respuesta.strip())
        except ValueError:
            return {"retry": True, "mensaje": "Por favor ingresa un número válido."}
    else:
        valor, msg = await _match_opcion_ai(
            respuesta,
            [o.texto for o in pregunta.opciones],
            multiple=(pregunta.tipo_pregunta_id == 4),
        )
        if valor is None:
            return {"retry": True, "mensaje": msg}

    # -------- Persistencia ------------------------------------------------ #
    r_enc = (
        db.query(RespuestaEncuesta)
        .filter(RespuestaEncuesta.entrega_id == conv.entrega_id)
        .first()
    )
    if not r_enc:
        r_enc = RespuestaEncuesta(entrega_id=conv.entrega_id)
        db.add(r_enc)
        db.commit()
        db.refresh(r_enc)

    if pregunta.tipo_pregunta_id == 1:
        db.add(RespuestaPregunta(respuesta_id=r_enc.id, pregunta_id=pregunta.id, texto=valor))
    elif pregunta.tipo_pregunta_id == 2:
        db.add(RespuestaPregunta(respuesta_id=r_enc.id, pregunta_id=pregunta.id, numero=valor))
    elif pregunta.tipo_pregunta_id == 3:
        db.add(
            RespuestaPregunta(
                respuesta_id=r_enc.id,
                pregunta_id=pregunta.id,
                opcion_id=pregunta.opciones[valor].id,
            )
        )
    else:  # multiselección
        for idx in valor:
            db.add(
                RespuestaPregunta(
                    respuesta_id=r_enc.id,
                    pregunta_id=pregunta.id,
                    opcion_id=pregunta.opciones[idx].id,
                )
            )

    db.commit()

    # -------- Siguiente pregunta ----------------------------------------- #
    todas = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta)
        .join(CampanaEncuesta)
        .join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == conv.entrega_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )
    pos = {p.id: i for i, p in enumerate(todas)}[pregunta.id]
    siguiente = todas[pos + 1] if pos + 1 < len(todas) else None

    # -------- Fin de encuesta -------------------------------------------- #
    if not siguiente:
        conv.completada = True
        db.commit()

        # marcar entrega respondida
        mark_as_responded(db, conv.entrega_id)

        # intento opcional de construir resumen (no interrumpe UX)
        try:
            await crear_respuesta_encuesta(db, conv.entrega_id, conv.historial)
        except Exception as exc:
            logger.warning("crear_respuesta_encuesta falló: %s", exc)

        return {"completada": True}

    # -------- Avanzar puntero -------------------------------------------- #
    conv.pregunta_actual_id = siguiente.id
    db.commit()

    salida: Dict[str, Any] = {
        "completada": False,
        "siguiente_pregunta": siguiente.texto,
        "tipo_pregunta": siguiente.tipo_pregunta_id,
    }
    if siguiente.tipo_pregunta_id in (3, 4):
        salida["opciones"] = [o.texto for o in siguiente.opciones]
    return salida


# --------------------------------------------------------------------------- #
# CREAR CONVERSACIÓN INICIAL
# --------------------------------------------------------------------------- #


async def iniciar_conversacion_whatsapp(
    db: Session,
    entrega_id: UUID,
) -> ConversacionEncuesta:
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.destinatario.telefono:
        raise ValueError("Entrega no válida o sin teléfono")

    primera = (
        db.query(PreguntaEncuesta)
        .join(PlantillaEncuesta)
        .join(CampanaEncuesta)
        .join(EntregaEncuesta)
        .filter(EntregaEncuesta.id == entrega_id)
        .order_by(PreguntaEncuesta.orden)
        .first()
    )
    if not primera:
        raise ValueError("La plantilla no tiene preguntas")

    conv = ConversacionEncuesta(
        entrega_id=entrega_id,
        completada=False,
        historial=[],
        pregunta_actual_id=primera.id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv
