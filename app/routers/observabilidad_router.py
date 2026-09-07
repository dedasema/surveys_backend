# app/routers/observabilidad_router.py
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.core.security import get_admin_user
from app.schemas.auth import TokenData
from app.services.quota_service import quota_tracker
from app.services.queue_service import get_queue_metrics

router = APIRouter(tags=["Admin - Observabilidad & Control de Cuota (RNF7, RNF5)"])

@router.get(
    "/admin/cuota/gemini",
    status_code=status.HTTP_200_OK,
    summary="Monitorización proactiva de cuota de Gemini API (RNF7)"
)
def get_cuota_gemini_endpoint(
    admin_data: TokenData = Depends(get_admin_user)
):
    """
    Retorna el estado en tiempo real del consumo y disponibilidad de la API de Gemini:
    - Estado actual: 'operativo' | 'en_espera_por_cuota'
    - Tiempo restante de espera/cooldown si se recibió un HTTP 429
    - Peticiones realizadas en la última hora y en el día
    - Historial de los últimos bloqueos por cuota
    """
    return quota_tracker.obtener_metricas_cuota()

@router.get(
    "/admin/observabilidad/metricas",
    status_code=status.HTTP_200_OK,
    summary="Métricas unificadas de telemetría del sistema (RNF5)"
)
def get_observabilidad_metricas_endpoint(
    formato: Optional[str] = Query("json", description="Formato de salida: 'json' o 'prometheus'"),
    admin_data: TokenData = Depends(get_admin_user)
):
    """
    Endpoint unificado de telemetría para administración:
    - Ingestión: mensajes por canal (gmail, ocr, voz, web), tasa/minuto, dead-letter.
    - Worker: latencia media, tareas encoladas vs procesadas.
    - Gemini API: llamadas totales, exitosas, fallos 429, latencias por tipo (texto, embeddings, multimodal, tools).
    - Integridad: verificaciones hash-chain realizadas, alteraciones detectadas.
    """
    colas_estado = get_queue_metrics()
    if formato == "prometheus":
        prom_text = quota_tracker.generar_prometheus_metrics(colas_estado)
        return PlainTextResponse(content=prom_text, media_type="text/plain; version=0.0.4")

    return quota_tracker.obtener_metricas_observabilidad(colas_estado)

@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Scraping estándar de métricas Prometheus (RNF5)"
)
def prometheus_metrics_endpoint():
    """
    Endpoint abierto estándar de Prometheus para recolección de métricas de telemetría.
    """
    colas_estado = get_queue_metrics()
    prom_text = quota_tracker.generar_prometheus_metrics(colas_estado)
    return PlainTextResponse(content=prom_text, media_type="text/plain; version=0.0.4")
