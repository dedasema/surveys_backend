# app/services/quota_service.py
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import deque

logger = logging.getLogger(__name__)

class QuotaAndTelemetryTracker:
    """
    Control de cuota proactivo de Gemini API (RNF7) y observabilidad unificada del sistema (RNF5).
    Registra contadores, latencias discriminadas por tipo (texto, embeddings, multimodal, tools),
    estados de cooldown por 429, historial de bloqueos, telemetría multicanal e integridad de datos.
    """
    def __init__(self):
        self.inicio_sistema = time.time()
        
        # Gemini API metrics (RNF7)
        self.total_llamadas = 0
        self.llamadas_exitosas = 0
        self.errores_cuota_429 = 0
        self.otros_errores = 0
        self.latencia_acumulada_ms = 0.0
        self.en_espera_hasta = 0.0
        self.ultimo_evento = datetime.now(timezone.utc).isoformat()
        
        # Historial de llamadas y bloqueos (últimas 24h / eventos)
        self._historial_llamadas_ts: deque = deque(maxlen=10000)
        self.historial_bloqueos: List[Dict[str, Any]] = []
        
        # Desglose por tipo de llamada Gemini (texto, embeddings, multimodal, tools)
        self.llamadas_por_tipo: Dict[str, int] = {
            "texto": 0,
            "embeddings": 0,
            "multimodal": 0,
            "tools": 0
        }
        self.latencia_por_tipo: Dict[str, float] = {
            "texto": 0.0,
            "embeddings": 0.0,
            "multimodal": 0.0,
            "tools": 0.0
        }
        
        # Ingestión multicanal (RNF5)
        self.ingesta_por_canal: Dict[str, int] = {
            "gmail": 0,
            "ocr": 0,
            "voz": 0,
            "web": 0,
            "whatsapp": 0
        }
        self._historial_ingesta_ts: deque = deque(maxlen=10000)
        
        # Telemetría de integridad criptográfica Hash-Chain (RNF8 / RNF5)
        self.verificaciones_integridad = 0
        self.alteraciones_detectadas = 0
        self.ultima_verificacion: Optional[str] = None
        
        # Telemetría del Worker
        self.worker_latencia_acumulada_ms = 0.0
        self.worker_tareas_procesadas = 0

    # -------------------------------------------------------------
    # Métodos para Gemini API & Cuota (RNF7)
    # -------------------------------------------------------------
    def registrar_inicio(self, tipo: str = "texto") -> float:
        """Registra el inicio de una llamada a Gemini"""
        ahora = time.time()
        self.total_llamadas += 1
        if tipo in self.llamadas_por_tipo:
            self.llamadas_por_tipo[tipo] += 1
        else:
            self.llamadas_por_tipo["texto"] += 1
        
        self._historial_llamadas_ts.append(ahora)
        self.ultimo_evento = datetime.now(timezone.utc).isoformat()
        return ahora

    def registrar_exito(self, inicio_ts: float, tipo: str = "texto"):
        """Registra el término exitoso de una llamada a Gemini"""
        duracion_ms = (time.time() - inicio_ts) * 1000.0
        self.llamadas_exitosas += 1
        self.latencia_acumulada_ms += duracion_ms
        if tipo in self.latencia_por_tipo:
            self.latencia_por_tipo[tipo] += duracion_ms
        else:
            self.latencia_por_tipo["texto"] += duracion_ms
        self.ultimo_evento = datetime.now(timezone.utc).isoformat()

    def registrar_429(self, inicio_ts: float, tipo: str = "texto", cooldown_segundos: int = 15, modelo: str = ""):
        """
        Registra un error HTTP 429 de cuota agotada, activa el cooldown y archiva en historial_bloqueos.
        """
        duracion_ms = (time.time() - inicio_ts) * 1000.0
        self.errores_cuota_429 += 1
        self.latencia_acumulada_ms += duracion_ms
        if tipo in self.latencia_por_tipo:
            self.latencia_por_tipo[tipo] += duracion_ms
        
        ahora = time.time()
        self.en_espera_hasta = ahora + cooldown_segundos
        self.ultimo_evento = datetime.now(timezone.utc).isoformat()
        
        evento_bloqueo = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cooldown_segundos": cooldown_segundos,
            "tipo": tipo,
            "modelo": modelo or "gemini",
            "motivo": "HTTP 429 Too Many Requests / Cuota Excedida"
        }
        self.historial_bloqueos.append(evento_bloqueo)
        if len(self.historial_bloqueos) > 30:
            self.historial_bloqueos.pop(0)

        logger.warning(
            "Límite de cuota Gemini (HTTP 429) alcanzado [%s]. Estado puesto 'en espera por cuota' por %ds",
            tipo, cooldown_segundos
        )

    def registrar_error(self, inicio_ts: float, tipo: str = "texto"):
        """Registra un error no relacionado a cuota"""
        duracion_ms = (time.time() - inicio_ts) * 1000.0
        self.otros_errores += 1
        self.latencia_acumulada_ms += duracion_ms
        if tipo in self.latencia_por_tipo:
            self.latencia_por_tipo[tipo] += duracion_ms
        self.ultimo_evento = datetime.now(timezone.utc).isoformat()

    def esta_en_espera_por_cuota(self) -> bool:
        """Indica si el sistema se encuentra temporalmente bloqueado por rate limit"""
        return time.time() < self.en_espera_hasta

    def obtener_estado(self) -> str:
        """Retorna 'en_espera_por_cuota' u 'operativo'"""
        return "en_espera_por_cuota" if self.esta_en_espera_por_cuota() else "operativo"

    def segundos_restantes_espera(self) -> int:
        """Segundos restantes del período de cooldown"""
        restante = int(self.en_espera_hasta - time.time())
        return max(0, restante)

    def peticiones_en_ventana(self, segundos: int) -> int:
        """Calcula peticiones en una ventana móvil de tiempo (ej. última hora o último día)"""
        limite = time.time() - segundos
        return sum(1 for ts in self._historial_llamadas_ts if ts >= limite)

    def obtener_metricas_cuota(self) -> Dict[str, Any]:
        """
        Retorna las métricas requeridas por el endpoint GET /admin/cuota/gemini (RNF7).
        """
        promedio_ms = (
            round(self.latencia_acumulada_ms / self.total_llamadas, 1)
            if self.total_llamadas > 0 else 0.0
        )
        return {
            "estado": self.obtener_estado(),
            "en_espera_por_cuota": self.esta_en_espera_por_cuota(),
            "segundos_restantes_espera": self.segundos_restantes_espera(),
            "peticiones_ultima_hora": self.peticiones_en_ventana(3600),
            "peticiones_hoy": self.peticiones_en_ventana(86400),
            "total_llamadas_historico": self.total_llamadas,
            "llamadas_exitosas": self.llamadas_exitosas,
            "errores_cuota_429": self.errores_cuota_429,
            "otros_errores": self.otros_errores,
            "latencia_promedio_ms": promedio_ms,
            "historial_bloqueos": list(reversed(self.historial_bloqueos[-10:])),
            "ultimo_evento": self.ultimo_evento
        }

    # -------------------------------------------------------------
    # Métodos para Ingesta Multicanal, Worker e Integridad (RNF5)
    # -------------------------------------------------------------
    def registrar_ingesta(self, canal: str):
        """Registra la recepción de un mensaje de un canal específico"""
        c = canal.lower().strip()
        if c in self.ingesta_por_canal:
            self.ingesta_por_canal[c] += 1
        else:
            self.ingesta_por_canal[c] = 1
        self._historial_ingesta_ts.append(time.time())

    def tasa_ingesta_por_minuto(self) -> float:
        """Calcula la tasa de mensajes recibidos por minuto en los últimos 5 minutos"""
        limite = time.time() - 300
        mensajes_recientes = sum(1 for ts in self._historial_ingesta_ts if ts >= limite)
        return round(mensajes_recientes / 5.0, 2)

    def registrar_procesamiento_worker(self, duracion_ms: float):
        """Registra la finalización de una tarea procesada por el worker"""
        self.worker_tareas_procesadas += 1
        self.worker_latencia_acumulada_ms += duracion_ms

    def registrar_verificacion_integridad(self, integro: bool, total_alteraciones: int = 0):
        """Registra la ejecución de una auditoría criptográfica de cadena (RNF8)"""
        self.verificaciones_integridad += 1
        if not integro or total_alteraciones > 0:
            self.alteraciones_detectadas += total_alteraciones
        self.ultima_verificacion = datetime.now(timezone.utc).isoformat()

    def obtener_metricas_observabilidad(self, colas_estado: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retorna las métricas consolidadas para GET /admin/observabilidad/metricas (RNF5).
        """
        # Latencias medias por tipo
        latencias_medias_por_tipo = {}
        for tipo, llamadas in self.llamadas_por_tipo.items():
            if llamadas > 0:
                latencias_medias_por_tipo[tipo] = round(self.latencia_por_tipo[tipo] / llamadas, 1)
            else:
                latencias_medias_por_tipo[tipo] = 0.0

        latencia_worker_media = (
            round(self.worker_latencia_acumulada_ms / self.worker_tareas_procesadas, 1)
            if self.worker_tareas_procesadas > 0 else 0.0
        )

        colas = colas_estado or {}

        return {
            "ingestion": {
                "mensajes_por_canal": dict(self.ingesta_por_canal),
                "total_recibidos": sum(self.ingesta_por_canal.values()),
                "tasa_procesamiento_por_minuto": self.tasa_ingesta_por_minuto(),
                "mensajes_fallidos_dead_letter": colas.get("fallidos", 0)
            },
            "worker": {
                "latencia_media_ms": latencia_worker_media,
                "tareas_procesadas": colas.get("procesados_total", self.worker_tareas_procesadas),
                "tareas_encoladas": colas.get("pendientes", 0),
                "tareas_en_proceso": colas.get("en_proceso", 0),
                "tareas_fallidas": colas.get("fallidos", 0),
                "broker": colas.get("broker", "in_memory")
            },
            "gemini_api": {
                "estado_cuota": self.obtener_estado(),
                "en_espera_por_cuota": self.esta_en_espera_por_cuota(),
                "segundos_restantes_espera": self.segundos_restantes_espera(),
                "llamadas_totales": self.total_llamadas,
                "llamadas_exitosas": self.llamadas_exitosas,
                "fallos_429": self.errores_cuota_429,
                "otros_fallos": self.otros_errores,
                "latencia_media_ms": round(self.latencia_acumulada_ms / self.total_llamadas, 1) if self.total_llamadas > 0 else 0.0,
                "llamadas_por_tipo": dict(self.llamadas_por_tipo),
                "latencia_media_por_tipo_ms": latencias_medias_por_tipo
            },
            "integridad_hash_chain": {
                "verificaciones_realizadas": self.verificaciones_integridad,
                "alteraciones_detectadas": self.alteraciones_detectadas,
                "ultima_verificacion": self.ultima_verificacion
            },
            "sistema": {
                "uptime_segundos": int(time.time() - self.inicio_sistema),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }

    def generar_prometheus_metrics(self, colas_estado: Optional[Dict[str, Any]] = None) -> str:
        """
        Genera el formato estándar de texto de Prometheus para scraping (/metrics).
        """
        m = self.obtener_metricas_observabilidad(colas_estado)
        lines = [
            "# HELP surveys_gemini_calls_total Total de llamadas a Gemini API",
            "# TYPE surveys_gemini_calls_total counter",
            f"surveys_gemini_calls_total {m['gemini_api']['llamadas_totales']}",
            "# HELP surveys_gemini_429_errors_total Total de errores 429 de cuota",
            "# TYPE surveys_gemini_429_errors_total counter",
            f"surveys_gemini_429_errors_total {m['gemini_api']['fallos_429']}",
            "# HELP surveys_gemini_latency_ms_avg Latencia promedio de llamadas a Gemini en ms",
            "# TYPE surveys_gemini_latency_ms_avg gauge",
            f"surveys_gemini_latency_ms_avg {m['gemini_api']['latencia_media_ms']}",
            "# HELP surveys_queue_pending_tasks Tareas pendientes en la cola",
            "# TYPE surveys_queue_pending_tasks gauge",
            f"surveys_queue_pending_tasks {m['worker']['tareas_encoladas']}",
            "# HELP surveys_queue_failed_tasks Tareas en dead-letter / fallidas",
            "# TYPE surveys_queue_failed_tasks gauge",
            f"surveys_queue_failed_tasks {m['worker']['tareas_fallidas']}",
            "# HELP surveys_integrity_alterations_detected Total de alteraciones detectadas en hash-chain",
            "# TYPE surveys_integrity_alterations_detected counter",
            f"surveys_integrity_alterations_detected {m['integridad_hash_chain']['alteraciones_detectadas']}",
        ]
        for canal, count in m["ingestion"]["mensajes_por_canal"].items():
            lines.append(f'surveys_ingestion_messages_total{{canal="{canal}"}} {count}')
        return "\n".join(lines) + "\n"

# Singleton exportado para toda la aplicación
quota_tracker = QuotaAndTelemetryTracker()
