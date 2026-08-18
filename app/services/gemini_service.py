import os
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

def get_gemini_api_key() -> str:
    key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    return key.strip() if key else ""

MODELS_TO_TRY = [
    "gemini-2.0-flash-lite",   # Verified — fastest, lowest quota cost
    "gemini-2.0-flash",        # Verified — fast fallback
    "gemini-3.5-flash-lite",   # Verified — newer, separate quota pool
    "gemini-3.6-flash",        # Verified — newest available
]

async def _execute_gemini_request(client: httpx.AsyncClient, api_key: str, payload: dict) -> httpx.Response:
    """
    Intenta ejecutar la petición contra Gemini con presupuesto acotado de latencia (máximo 1 reintento de 1.5s).
    """
    import asyncio
    last_res = None
    
    # 1. Primer intento con los modelos rápidos
    for model in MODELS_TO_TRY:
        url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"
        res = await client.post(url, json=payload)
        if res.status_code == 200:
            return res
        last_res = res

    # 2. Si el servidor respondió 429 (límite de ráfaga), hacer UN solo reintento de 1.5s
    if last_res and last_res.status_code == 429:
        await asyncio.sleep(1.5)
        for model in MODELS_TO_TRY:
            url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                return res
            last_res = res

    # 3. Si falló por formato de herramientas (tools), reintentar mensaje plano sin tools
    if "tools" in payload:
        payload_no_tools = {k: v for k, v in payload.items() if k != "tools"}
        for model in MODELS_TO_TRY:
            url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"
            res = await client.post(url, json=payload_no_tools)
            if res.status_code == 200:
                return res
            last_res = res

    return last_res

async def call_gemini_text(prompt: str, system_instruction: str = "") -> str:
    """
    Realiza una consulta de texto simple a la API de Gemini (puerto 443 HTTPS).
    No requiere librerías pesadas, usa httpx directamente.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurada")

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
        res = await _execute_gemini_request(client, api_key, payload)
        if res.status_code != 200:
            if res.status_code == 429:
                raise RuntimeError("La API de Gemini en Google AI Studio ha alcanzado la cuota del plan gratuito. Reintenta en unos segundos.")
            raise RuntimeError(f"Error llamando a Gemini API ({res.status_code}): {res.text}")

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

def _convert_to_gemini_schema(schema: Any) -> Any:
    """Convierte los tipos de esquema de OpenAI (lowercase) al formato OpenAPI de Gemini (UPPERCASE)."""
    if not isinstance(schema, dict):
        return schema
    converted = {}
    for k, v in schema.items():
        if k == "nullable":
            continue
        elif k == "type" and isinstance(v, str):
            converted[k] = v.upper()
        elif isinstance(v, dict):
            converted[k] = _convert_to_gemini_schema(v)
        elif isinstance(v, list):
            converted[k] = [_convert_to_gemini_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            converted[k] = v
    return converted

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
        # Convertir tools estilo OpenAI a formato Gemini (con tipos en MAYÚSCULAS)
        function_declarations = []
        for t in tools:
            if t.get("type") == "function":
                fn = t["function"]
                function_declarations.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": _convert_to_gemini_schema(fn.get("parameters", {}))
                })
        if function_declarations:
            payload["tools"] = [{"functionDeclarations": function_declarations}]

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await _execute_gemini_request(client, api_key, payload)
        if res.status_code != 200:
            if res.status_code == 429:
                raise RuntimeError("La cuota gratuita de tu API Key de Gemini se ha pausado por límite de peticiones. Por favor reintenta en 30 segundos.")
            raise RuntimeError(f"Gemini API ({res.status_code}): {res.text}")

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
