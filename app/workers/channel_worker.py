# app/workers/channel_worker.py
import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.services.queue_service import (
    get_redis_client,
    QUEUE_KEY,
    PROCESSING_KEY,
    FAILED_KEY,
    STATS_PROCESSED_KEY,
    STATS_FAILED_KEY,
    _in_memory_queue,
    _in_memory_failed
)
from app.core.database import SessionLocal
from app.services.hash_chain_service import vincular_hash_cadena

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChannelWorker")

async def procesar_mensaje_ingesta(task: Dict[str, Any]) -> bool:
    """
    Ejecuta el procesamiento del mensaje recibido de cualquier canal (Gmail, OCR, Voz).
    Vincula el hash-chain criptográfico (RNF8) y prepara la respuesta.
    """
    canal = task.get("canal")
    contenido = task.get("contenido")
    tipo = task.get("tipo")
    metadata = task.get("metadata", {})

    logger.info("Procesando tarea %s [Canal: %s, Tipo: %s]", task.get("id"), canal, tipo)

    # Simulación/Ejecución de procesamiento
    # En próximas fases (RF20/RF18), aquí se invocará a Gemini multimodal o transcripción
    time.sleep(0.1)  # Simular latencia de parsing/normalización

    return True

def handle_task_failure(r, task: Dict[str, Any], error_msg: str):
    """Maneja los reintentos exponenciales (hasta 3) o transfiere a la cola de fallidos (Dead-Letter)"""
    task["intentos"] = task.get("intentos", 0) + 1
    task["ultimo_error"] = error_msg
    task["actualizado_en"] = datetime.now(timezone.utc).isoformat()

    if task["intentos"] < task.get("max_intentos", 3):
        backoff = 2 ** task["intentos"]
        logger.warning(
            "Tarea %s falló (intento %d/3). Reintentando en %d segundos. Error: %s",
            task["id"], task["intentos"], backoff, error_msg
        )
        time.sleep(backoff)
        payload_str = json.dumps(task, default=str)
        if r:
            r.rpush(QUEUE_KEY, payload_str)
        else:
            _in_memory_queue.append(task)
    else:
        logger.error("Tarea %s agotó los 3 reintentos. Marcada como FALLIDA/DEAD-LETTER.", task["id"])
        task["estado"] = "fallido"
        payload_str = json.dumps(task, default=str)
        if r:
            r.rpush(FAILED_KEY, payload_str)
            r.incr(STATS_FAILED_KEY)
            r.setex(f"surveys:task:{task['id']}", 86400 * 7, payload_str)
        else:
            _in_memory_failed.append(task)

async def run_worker_loop(run_once: bool = False):
    """
    Loop principal del worker consumidor.
    """
    logger.info("Iniciando ChannelWorker para ingesta asíncrona multicanal...")
    r = get_redis_client()

    while True:
        task = None
        raw_payload = None

        if r:
            try:
                # Extraer de forma bloqueante de la cola
                pop_res = r.blpop(QUEUE_KEY, timeout=2)
                if pop_res:
                    _, raw_payload = pop_res
                    task = json.loads(raw_payload)
                    r.sadd(PROCESSING_KEY, task["id"])
            except Exception as e:
                logger.error("Error leyendo de Redis: %s", e)
                await asyncio.sleep(1)
        else:
            if _in_memory_queue:
                task = _in_memory_queue.pop(0)

        if task:
            try:
                exito = await procesar_mensaje_ingesta(task)
                if exito:
                    if r:
                        r.srem(PROCESSING_KEY, task["id"])
                        r.incr(STATS_PROCESSED_KEY)
                        task["estado"] = "procesado"
                        r.setex(f"surveys:task:{task['id']}", 86400, json.dumps(task, default=str))
                    logger.info("Tarea %s procesada exitosamente.", task["id"])
                else:
                    raise RuntimeError("El procesamiento retornó falso")
            except Exception as e:
                logger.exception("Excepción procesando tarea %s: %s", task.get("id"), e)
                if r:
                    r.srem(PROCESSING_KEY, task.get("id"))
                handle_task_failure(r, task, str(e))
        else:
            if run_once:
                break
            await asyncio.sleep(0.2)

        if run_once and not _in_memory_queue:
            break

if __name__ == "__main__":
    asyncio.run(run_worker_loop())
