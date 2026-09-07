# app/services/queue_service.py
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "surveys:ingesta:queue"
PROCESSING_KEY = "surveys:ingesta:processing"
FAILED_KEY = "surveys:ingesta:failed"
STATS_PROCESSED_KEY = "surveys:ingesta:stats:processed"
STATS_FAILED_KEY = "surveys:ingesta:stats:failed"

_redis_client: Optional[redis.Redis] = None

# Fallback in-memory queue for environments without live Redis (e.g. lightweight unit tests)
_in_memory_queue = []
_in_memory_failed = []
_in_memory_processed_count = 0
_in_memory_tasks = {}

def get_redis_client() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        client = redis.from_url(
            settings.REDIS_URL or "redis://localhost:6379/0",
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0
        )
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as e:
        logger.warning("Redis no disponible en %s (%s). Usando cola en memoria como fallback.", settings.REDIS_URL, e)
        return None

def enqueue_channel_message(
    canal: str,
    contenido: Any,
    tipo: str = "texto",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Normaliza el mensaje de entrada (Gmail, OCR físico, Voz) y lo encola de inmediato
    para procesamiento asíncrono sin bloquear el canal de origen.
    """
    from app.services.quota_service import quota_tracker
    quota_tracker.registrar_ingesta(canal)

    task_id = str(uuid.uuid4())
    task_data = {
        "id": task_id,
        "canal": canal.lower().strip(),
        "contenido": contenido,
        "tipo": tipo.lower().strip(),
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "intentos": 0,
        "max_intentos": 3,
        "estado": "en_cola"
    }

    payload_str = json.dumps(task_data, default=str)
    r = get_redis_client()

    if r:
        try:
            r.rpush(QUEUE_KEY, payload_str)
            r.setex(f"surveys:task:{task_id}", 86400, payload_str)
        except Exception as e:
            logger.error("Error encolando en Redis: %s. Usando fallback en memoria.", e)
            _in_memory_queue.append(task_data)
            _in_memory_tasks[task_id] = task_data
    else:
        _in_memory_queue.append(task_data)
        _in_memory_tasks[task_id] = task_data

    return {
        "task_id": task_id,
        "canal": task_data["canal"],
        "estado": "recibido",
        "en_cola": True,
        "timestamp": task_data["timestamp"]
    }

def get_queue_metrics() -> Dict[str, Any]:
    """
    Retorna el estado de la cola en tiempo real (pendientes, en proceso, fallidos, procesados).
    """
    r = get_redis_client()
    if r:
        try:
            pendientes = r.llen(QUEUE_KEY)
            en_proceso = r.scard(PROCESSING_KEY)
            fallidos = r.llen(FAILED_KEY)
            procesados = int(r.get(STATS_PROCESSED_KEY) or 0)
            return {
                "broker": "redis",
                "activo": True,
                "pendientes": pendientes,
                "en_proceso": en_proceso,
                "fallidos": fallidos,
                "procesados_total": procesados
            }
        except Exception as e:
            logger.error("Error consultando métricas en Redis: %s", e)

    return {
        "broker": "in_memory_fallback",
        "activo": True,
        "pendientes": len(_in_memory_queue),
        "en_proceso": 0,
        "fallidos": len(_in_memory_failed),
        "procesados_total": _in_memory_processed_count
    }
