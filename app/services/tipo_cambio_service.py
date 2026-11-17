# app/services/tipo_cambio_service.py
import time
import logging
from typing import Tuple, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

URL_TIPO_CAMBIO_BCB = "https://apibcb.cucu.bo/api/v1/tc/oficial"
FALLBACK_TIPO_CAMBIO = 7.0

# Caché en memoria para evitar saturar la API en cada consulta
_tc_cache: Dict[str, Any] = {
    "valor": None,
    "fecha": None,
    "fuente": "Banco Central de Bolivia (bcb.gob.bo)",
    "timestamp": 0.0,
    "es_fallback": False
}
CACHE_TTL_SECONDS = 1800  # 30 minutos

async def obtener_tipo_cambio_oficial(forzar_refresco: bool = False) -> Tuple[float, bool, Dict[str, Any]]:
    """
    Obtiene el tipo de cambio oficial del dólar respecto al boliviano (USD/BOB).
    Fuente primaria: https://apibcb.cucu.bo/api/v1/tc/oficial
    Fallback obligatorio: 7.0 (en caso de error, timeout o respuesta no válida).

    Retorna: (valor_tc, es_fallback, metadata)
    """
    now = time.time()
    if not forzar_refresco and _tc_cache["valor"] is not None and (now - _tc_cache["timestamp"] < CACHE_TTL_SECONDS):
        return _tc_cache["valor"], _tc_cache["es_fallback"], _tc_cache

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(URL_TIPO_CAMBIO_BCB)
            if res.status_code == 200:
                data = res.json()
                tc_data = data.get("tc_oficial", {})
                valor = tc_data.get("valor") or tc_data.get("venta") or tc_data.get("compra")

                if valor is not None:
                    valor_float = float(valor)
                    if valor_float > 0:
                        _tc_cache["valor"] = valor_float
                        _tc_cache["fecha"] = tc_data.get("fecha")
                        _tc_cache["fuente"] = data.get("fuente", "Banco Central de Bolivia (bcb.gob.bo)")
                        _tc_cache["timestamp"] = now
                        _tc_cache["es_fallback"] = False
                        logger.info(f"Tipo de cambio oficial actualizado desde BCB: {valor_float} USD/BOB")
                        return valor_float, False, _tc_cache

            logger.warning(f"Respuesta inesperada de API BCB ({res.status_code}): {res.text}. Usando fallback {FALLBACK_TIPO_CAMBIO}")
    except Exception as exc:
        logger.warning(f"No se pudo consultar API de tipo de cambio ({exc}). Aplicando fallback oficial {FALLBACK_TIPO_CAMBIO}")

    # Fallback garantizado
    _tc_cache["valor"] = FALLBACK_TIPO_CAMBIO
    _tc_cache["fecha"] = None
    _tc_cache["fuente"] = "Fallback Sistema (7.00)"
    _tc_cache["timestamp"] = now
    _tc_cache["es_fallback"] = True
    return FALLBACK_TIPO_CAMBIO, True, _tc_cache
