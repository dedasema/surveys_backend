# app/services/embedding_service.py
import math
import logging
from typing import List, Optional
import httpx

from app.services.gemini_service import get_gemini_api_key

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"

async def generar_embedding(texto: str) -> List[float]:
    """
    Genera un vector embedding de 768 dimensiones para el texto dado usando Gemini (RF22).
    """
    if not texto or not texto.strip():
        return [0.0] * 768

    api_key = get_gemini_api_key()
    if not api_key:
        logger.warning("GEMINI_API_KEY no disponible para embeddings, retornando vector nulo")
        return [0.0] * 768

    url = f"{EMBEDDING_URL}?key={api_key}"
    payload = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {
            "parts": [{"text": texto[:2048]}]
        }
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                values = data.get("embedding", {}).get("values", [])
                if values and len(values) == 768:
                    return values
                elif values:
                    # Rellenar o truncar si el modelo entrega diferente dimensionalidad
                    if len(values) < 768:
                        return values + [0.0] * (768 - len(values))
                    return values[:768]
            else:
                logger.warning("Error llamando a Gemini embeddings (%s): %s", res.status_code, res.text)
    except Exception as e:
        logger.error("Excepción al generar embedding con Gemini: %s", e)

    # Fallback pseudo-determinístico para entornos de testing / offline
    return _generar_embedding_fallback(texto)

def _generar_embedding_fallback(texto: str) -> List[float]:
    """Genera un vector unitario normalizado determinístico de 768 dims para testing/fallback"""
    import hashlib
    h = hashlib.sha256(texto.encode("utf-8")).digest()
    vals = [((h[i % len(h)] / 255.0) * 2.0 - 1.0) for i in range(768)]
    norm = math.sqrt(sum(x * x for x in vals)) or 1.0
    return [x / norm for x in vals]

def similitud_coseno(v1: List[float], v2: List[float]) -> float:
    """
    Calcula la similitud coseno entre dos vectores (entre -1.0 y 1.0).
    """
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    return max(-1.0, min(1.0, dot / (norm1 * norm2)))
