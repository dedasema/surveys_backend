from __future__ import annotations
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

def _extract_text_and_payload(msg: Dict[str, Any]) -> Tuple[str, str]:
    """
    Devuelve (texto_visible, payload_id) a partir de un dict ``msg``.
    Si el mensaje no es texto / botón / lista, devuelve ("", "").
    """
    mtype = msg.get("type")

    if mtype == "button":                 #
        btn = msg.get("button", {})
        return btn.get("text", ""), btn.get("payload", "")

    if mtype == "interactive":
        data = msg.get("interactive", {})
        if data.get("type") == "button_reply":
            br = data["button_reply"]
            return br.get("title", ""), br.get("id", "")
        if data.get("type") == "list_reply":
            lr = data["list_reply"]
            return lr.get("title", ""), lr.get("id", "")

    if mtype == "reply":
        rep = msg.get("reply", {})
        if rep.get("type") == "buttons_reply":
            br = rep["buttons_reply"]
            return br.get("title", ""), br.get("id", "")
        if rep.get("type") == "list_reply":
            lr = rep["list_reply"]
            return lr.get("title", ""), lr.get("id", "")

    if mtype == "text" and msg.get("context", {}).get("id"):
        return msg["text"]["body"], ""            # payload vacío, texto visible

    if mtype == "text":
        return msg["text"]["body"], ""

    return "", ""


# --------------------------------------------------------------------------- #
# PARSER PRINCIPAL
# --------------------------------------------------------------------------- #

def parse_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza el webhook de Meta Cloud API y Whapi.
    """
    try:
        # 0.1 Meta Cloud API Structure
        if "entry" in payload and payload["entry"]:
            changes = payload["entry"][0].get("changes", [{}])
            val = changes[0].get("value", {}) if changes else {}
            if "messages" in val and val["messages"]:
                msg = val["messages"][0]
                from_num = msg.get("from", "")
                text, payload_id = _extract_text_and_payload(msg)
                return {
                    "kind": "message",
                    "from_number": from_num,
                    "text": text or payload_id,
                    "payload_id": payload_id,
                    "message_id": msg.get("id"),
                    "timestamp": msg.get("timestamp"),
                    "interactive": msg.get("type") in ("button", "interactive", "reply"),
                    "raw": payload,
                }
            if "statuses" in val:
                return {
                    "kind": "status",
                    "status": val.get("statuses", [{}])[0],
                    "raw": payload,
                }

        # 0.2 Whapi Notifications
        if "statuses" in payload:
            return {
                "kind": "status",
                "status": payload.get("statuses", [{}])[0],
                "raw": payload,
            }

        if "messages" not in payload or not payload["messages"]:
            return {"kind": "unknown", "raw": payload}

        msg = payload["messages"][0]

        if msg.get("from_me", False):
            return {"kind": "own", "raw": payload}

        text, payload_id = _extract_text_and_payload(msg)

        if not text and not payload_id:
            return {
                "kind": "non_text",
                "subtype": msg.get("type", "unknown"),
                "raw": payload,
            }

        interactive_types = {"button", "interactive", "reply"}
        return {
            "kind": "message",
            "from_number": msg.get("from", "").split("@")[0],
            "text": text or payload_id,               # prioriza texto visible
            "payload_id": payload_id,
            "message_id": msg.get("id"),
            "timestamp": msg.get("timestamp"),
            "interactive": msg.get("type") in interactive_types,
            "raw": payload,
        }

    except Exception as exc:  # pragma: no cover
        logger.exception("Error al parsear webhook: %s", exc)
        return {"kind": "error", "error": str(exc), "raw": payload}
