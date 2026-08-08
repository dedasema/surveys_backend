# app/services/gemini_service.py
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

def get_gemini_api_key() -> str:
    return (settings.GEMINI_API_KEY or "").strip()

async def call_gemini_text(prompt: str, system_instruction: str = "") -> str:
    """
    Realiza una consulta de texto simple a la API de Gemini (puerto 443 HTTPS).
    No requiere librerías pesadas, usa httpx directamente.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurada")

    model = settings.GEMINI_MODEL or "gemini-2.0-flash"
    url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.3
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(url, json=payload)
        if res.status_code != 200:
            logger.error(f"Error en Gemini API status {res.status_code}: {res.text}")
            # Intentar fallback a gemini-1.5-flash si falló
            if "gemini-2.0" in model:
                fallback_url = f"{GEMINI_BASE_URL}/gemini-1.5-flash:generateContent?key={api_key}"
                res = await client.post(fallback_url, json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Error llamando a Gemini API: {res.text}")
            else:
                raise RuntimeError(f"Error llamando a Gemini API: {res.text}")

        data = res.json()
        try:
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return ""
        except Exception as e:
            logger.error(f"Error parseando respuesta de Gemini: {e}")
            return ""

async def call_gemini_chat_with_tools(
    system_instruction: str,
    user_message: str,
    tools: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Permite enviar chat a Gemini con soporte de Function Calling (Tools).
    Devuelve dict con 'text' o 'tool_call' (name, args).
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurada")

    model = settings.GEMINI_MODEL or "gemini-2.0-flash"
    url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_message}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": 0.3
        }
    }

    if tools:
        # Convertir tools estilo OpenAI a formato Gemini
        function_declarations = []
        for t in tools:
            if t.get("type") == "function":
                fn = t["function"]
                function_declarations.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {})
                })
        if function_declarations:
            payload["tools"] = [{"functionDeclarations": function_declarations}]

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(url, json=payload)
        if res.status_code != 200:
            logger.error(f"Error Gemini Chat API status {res.status_code}: {res.text}")
            raise RuntimeError(f"Error llamando a Gemini Chat API: {res.text}")

        data = res.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return {"type": "text", "text": "Sin respuesta de Gemini"}

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return {"type": "text", "text": ""}

        part = parts[0]
        # Verificar si Gemini devolvió un Function Call
        if "functionCall" in part:
            fc = part["functionCall"]
            return {
                "type": "tool_call",
                "name": fc.get("name"),
                "args": fc.get("args", {})
            }

        return {
            "type": "text",
            "text": part.get("text", "").strip()
        }
