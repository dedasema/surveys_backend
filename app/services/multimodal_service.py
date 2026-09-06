# app/services/multimodal_service.py
import base64
import json
import logging
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.services.gemini_service import get_gemini_api_key, MODELS_TO_TRY, GEMINI_BASE_URL, _execute_gemini_request

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB

ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp"
}

ALLOWED_AUDIO_TYPES = {
    "audio/mp3", "audio/mpeg", "audio/wav", "audio/ogg", "audio/x-wav", "audio/m4a", "audio/x-m4a"
}

ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_AUDIO_TYPES | {"text/plain"}

def validar_archivo_multimodal(contenido_bytes: bytes, mime_type: str) -> None:
    """Valida el tipo MIME y tamaño máximo para evitar consumo innecesario de cuota"""
    mime_limpio = mime_type.lower().split(";")[0].strip()
    if mime_limpio not in ALLOWED_TYPES:
        raise ValueError(f"Tipo de archivo no permitido: '{mime_type}'. Permitidos: {', '.join(sorted(ALLOWED_TYPES))}")

    if len(contenido_bytes) > MAX_FILE_SIZE_BYTES:
        mb = len(contenido_bytes) / (1024 * 1024)
        raise ValueError(f"El archivo supera el tamaño máximo permitido de 15 MB ({mb:.2f} MB)")

async def interpretar_multimodal(
    contenido_bytes: bytes,
    mime_type: str,
    prompt_instruccion: str,
    schema_salida: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Servicio centralizado de comprensión multimodal para Gemini (RF20).
    Acepta audio, imagen o texto y devuelve una interpretación consistente.
    """
    validar_archivo_multimodal(contenido_bytes, mime_type)

    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurada")

    mime_limpio = mime_type.lower().split(";")[0].strip()
    base64_data = base64.b64encode(contenido_bytes).decode("utf-8")

    parts = [
        {"text": prompt_instruccion},
        {
            "inlineData": {
                "mimeType": mime_limpio,
                "data": base64_data
            }
        }
    ]

    generation_config: Dict[str, Any] = {
        "temperature": 0.2
    }

    if schema_salida:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = schema_salida

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": parts
            }
        ],
        "generationConfig": generation_config
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        res = await _execute_gemini_request(client, api_key, payload)
        if res.status_code != 200:
            if res.status_code == 429:
                raise RuntimeError("Cuota temporal de Gemini alcanzada. Reintente en unos segundos.")
            raise RuntimeError(f"Error en Gemini Multimodal ({res.status_code}): {res.text}")

        data = res.json()
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                return {"texto": "", "interpretacion": None}

            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

            if schema_salida or (raw_text.startswith("{") and raw_text.endswith("}")):
                try:
                    return {"texto": raw_text, "interpretacion": json.loads(raw_text)}
                except Exception:
                    pass

            return {"texto": raw_text, "interpretacion": None}
        except Exception as e:
            logger.error("Error parseando respuesta multimodal: %s", e)
            return {"texto": "", "error": str(e)}

async def transcribir_audio(audio_bytes: bytes, mime_type: str) -> str:
    """
    Especialización para transcripción de respuestas grabadas por voz (RF18).
    Devuelve la transcripción limpia y fiel en lenguaje natural.
    """
    prompt = (
        "Eres un transcriptor de audio para encuestas de satisfacción. "
        "Transcribe textualmente el contenido del siguiente audio en español. "
        "Devuelve únicamente la transcripción exacta, sin comentarios, sin introducciones ni etiquetas adicionales."
    )
    resultado = await interpretar_multimodal(
        contenido_bytes=audio_bytes,
        mime_type=mime_type,
        prompt_instruccion=prompt
    )
    return resultado.get("texto", "").strip()
