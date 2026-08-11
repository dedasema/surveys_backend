
from __future__ import annotations

import re
import logging
from typing import List, Tuple, Dict, Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)



def _normalize_number(numero: str) -> str:
    """Deja solo dígitos: '59171234567@c.us' -> '59171234567'."""
    if "@c.us" in numero:
        numero = numero.split("@")[0]
    return re.sub(r"[^0-9]", "", numero)


async def _send_meta_cloud(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Envía mensajes utilizando la API Oficial de Meta WhatsApp Cloud API."""
    token = settings.WHATSAPP_TOKEN
    phone_id = settings.WHATSAPP_PHONE_ID
    if not token or not phone_id:
        return {"success": False, "error": "Faltan credenciales WHATSAPP_TOKEN o WHATSAPP_PHONE_ID"}

    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code >= 300:
            logger.error("Meta WhatsApp Cloud API Error %s -> %s\n%s", url, resp.status_code, resp.text)
            return {"success": False, "status_code": resp.status_code, "error": resp.text}

        return {"success": True, "response": resp.json()}
    except Exception as exc:
        logger.exception("Error contactando Meta WhatsApp API: %s", exc)
        return {"success": False, "error": str(exc)}


async def _post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST genérico con manejo de errores y logging (Whapi Fallback)."""
    headers = {
        "Authorization": f"Bearer {settings.WHAPI_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    url = f"{settings.WHAPI_API_URL}{endpoint}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code >= 300:
            logger.error("Whapi %s %s -> %s\n%s", endpoint, payload, resp.status_code, resp.text)
            return {"success": False, "status_code": resp.status_code, "error": resp.text}

        return {"success": True, "response": resp.json()}

    except Exception as exc:  # pragma: no cover
        logger.exception("Error contactando Whapi: %s", exc)
        return {"success": False, "error": str(exc)}


# --------------------------------------------------------------------------- #
# Helpers de envío
# --------------------------------------------------------------------------- #

def _payload_text(to: str, body: str) -> Dict[str, Any]:
    return {"to": to, "body": body}


def _payload_confirm(to: str, body: str) -> Dict[str, Any]:
    """Botones rápidos Sí/No (quick-reply)."""
    return {
        "to": to,
        "type": "button",
        "header": {"text": "Confirmación"},
        "body": {"text": body},
        "footer": {"text": "Toca un botón para continuar"},
        "action": {
            "buttons": [
                {"type": "quick_reply", "title": "Sí", "id": "btn_si"},
                {"type": "quick_reply", "title": "No", "id": "btn_no"},
            ]
        },
    }


def _payload_list(to: str, body: str, opciones: List[str]) -> Dict[str, Any]:
    """Lista de selección única."""
    rows = [{"id": f"opt_{i}", "title": op[:24]} for i, op in enumerate(opciones)]
    return {
        "to": to,
        "type": "list",
        "header": {"text": "Pregunta"},
        "body": {"text": body},
        "action": {
            "list": {
                "sections": [{"title": "Opciones", "rows": rows}],
                "label": "Ver opciones",
            }
        },
    }


def _payload_buttons(
    to: str, body: str, buttons: List[Tuple[str, str]]
) -> Dict[str, Any]:
    """Botones rápidos personalizados (máx. 3)."""
    assert 1 <= len(buttons) <= 3, "WhatsApp permite entre 1 y 3 botones"
    btn_objs = [{"type": "quick_reply", "title": t[:20], "id": pid} for t, pid in buttons]
    return {
        "to": to,
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": btn_objs},
    }


async def send_text(numero: str, texto: str) -> Dict[str, Any]:
    to = _normalize_number(numero)
    if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": texto}
        }
        return await _send_meta_cloud(payload)
    return await _post("/messages/text", _payload_text(to, texto))


async def send_confirm(numero: str, texto: str) -> Dict[str, Any]:
    to = _normalize_number(numero)
    if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "btn_si", "title": "Sí"}},
                        {"type": "reply", "reply": {"id": "btn_no", "title": "No"}}
                    ]
                }
            }
        }
        return await _send_meta_cloud(payload)
    return await _post("/messages/interactive", _payload_confirm(to, texto))


async def send_list(numero: str, pregunta: str, opciones: List[str]) -> Dict[str, Any]:
    to = _normalize_number(numero)
    if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
        rows = [{"id": f"opt_{i}", "title": op[:24]} for i, op in enumerate(opciones[:10])]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": "Encuesta"},
                "body": {"text": pregunta[:1024]},
                "footer": {"text": "Selecciona una opción"},
                "action": {
                    "button": "Ver Opciones",
                    "sections": [{"title": "Opciones Válidas", "rows": rows}]
                }
            }
        }
        return await _send_meta_cloud(payload)
    return await _post("/messages/interactive", _payload_list(to, pregunta, opciones))


async def send_buttons(
    numero: str, cuerpo: str, botones: List[Tuple[str, str]]
) -> Dict[str, Any]:
    to = _normalize_number(numero)
    if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
        btn_objs = [{"type": "reply", "reply": {"id": pid, "title": t[:20]}} for t, pid in botones[:3]]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": cuerpo},
                "action": {"buttons": btn_objs}
            }
        }
        return await _send_meta_cloud(payload)
    return await _post("/messages/interactive", _payload_buttons(to, cuerpo, botones))


async def send_raw(payload: Dict[str, Any]) -> Dict[str, Any]:
    if "to" not in payload:
        raise ValueError("El payload debe incluir el campo 'to'")
    payload = payload.copy()
    payload["to"] = _normalize_number(payload["to"])
    if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
        return await _send_meta_cloud(payload)
    endpoint = (
        "/messages/interactive"
        if payload.get("type") in ("button", "list")
        else "/messages/text"
    )
    return await _post(endpoint, payload)