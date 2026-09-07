# tests/test_software2_phase5.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.quota_service import QuotaAndTelemetryTracker, quota_tracker
from app.core.security import get_admin_user
from app.schemas.auth import TokenData

@pytest.fixture
def admin_override():
    app.dependency_overrides[get_admin_user] = lambda: TokenData(
        sub="admin@test.com",
        rol="admin",
        tipo_usuario="administrador"
    )
    yield
    app.dependency_overrides.pop(get_admin_user, None)

@pytest.fixture
def client():
    return TestClient(app)

def test_quota_tracker_initial_state():
    tracker = QuotaAndTelemetryTracker()
    assert tracker.obtener_estado() == "operativo"
    assert tracker.esta_en_espera_por_cuota() is False
    assert tracker.segundos_restantes_espera() == 0

def test_quota_tracker_handles_429_cooldown():
    tracker = QuotaAndTelemetryTracker()
    inicio = tracker.registrar_inicio(tipo="texto")
    tracker.registrar_429(inicio, tipo="texto", cooldown_segundos=10, modelo="gemini-2.0-flash")

    assert tracker.esta_en_espera_por_cuota() is True
    assert tracker.obtener_estado() == "en_espera_por_cuota"
    assert tracker.segundos_restantes_espera() > 0
    assert tracker.errores_cuota_429 == 1
    assert len(tracker.historial_bloqueos) == 1
    assert tracker.historial_bloqueos[0]["cooldown_segundos"] == 10
    assert tracker.historial_bloqueos[0]["modelo"] == "gemini-2.0-flash"

def test_quota_tracker_metrics_by_call_type():
    tracker = QuotaAndTelemetryTracker()
    
    # Simular texto
    t1 = tracker.registrar_inicio(tipo="texto")
    tracker.registrar_exito(t1, tipo="texto")
    
    # Simular embeddings
    t2 = tracker.registrar_inicio(tipo="embeddings")
    tracker.registrar_exito(t2, tipo="embeddings")
    
    # Simular multimodal
    t3 = tracker.registrar_inicio(tipo="multimodal")
    tracker.registrar_exito(t3, tipo="multimodal")
    
    # Simular tools
    t4 = tracker.registrar_inicio(tipo="tools")
    tracker.registrar_exito(t4, tipo="tools")
    
    metrics = tracker.obtener_metricas_observabilidad()
    assert metrics["gemini_api"]["llamadas_totales"] == 4
    assert metrics["gemini_api"]["llamadas_exitosas"] == 4
    assert metrics["gemini_api"]["llamadas_por_tipo"]["texto"] == 1
    assert metrics["gemini_api"]["llamadas_por_tipo"]["embeddings"] == 1
    assert metrics["gemini_api"]["llamadas_por_tipo"]["multimodal"] == 1
    assert metrics["gemini_api"]["llamadas_por_tipo"]["tools"] == 1

def test_quota_tracker_channel_ingestion_telemetry():
    tracker = QuotaAndTelemetryTracker()
    tracker.registrar_ingesta("gmail")
    tracker.registrar_ingesta("voz")
    tracker.registrar_ingesta("ocr")
    tracker.registrar_ingesta("web")
    tracker.registrar_ingesta("whatsapp")

    metrics = tracker.obtener_metricas_observabilidad()
    ing = metrics["ingestion"]
    assert ing["mensajes_por_canal"]["gmail"] == 1
    assert ing["mensajes_por_canal"]["voz"] == 1
    assert ing["mensajes_por_canal"]["ocr"] == 1
    assert ing["mensajes_por_canal"]["web"] == 1
    assert ing["mensajes_por_canal"]["whatsapp"] == 1
    assert ing["total_recibidos"] == 5

def test_endpoint_admin_cuota_gemini(client, admin_override):
    res = client.get("/admin/cuota/gemini")
    assert res.status_code == 200
    data = res.json()
    assert "estado" in data
    assert "en_espera_por_cuota" in data
    assert "segundos_restantes_espera" in data
    assert "peticiones_ultima_hora" in data
    assert "peticiones_hoy" in data
    assert "historial_bloqueos" in data

def test_endpoint_admin_observabilidad_metricas(client, admin_override):
    res = client.get("/admin/observabilidad/metricas")
    assert res.status_code == 200
    data = res.json()
    assert "ingestion" in data
    assert "worker" in data
    assert "gemini_api" in data
    assert "integridad_hash_chain" in data
    assert "sistema" in data

def test_endpoint_observabilidad_prometheus(client, admin_override):
    # Probar endpoint /metrics abierto
    res1 = client.get("/metrics")
    assert res1.status_code == 200
    assert "surveys_gemini_calls_total" in res1.text
    assert "surveys_queue_pending_tasks" in res1.text

    # Probar endpoint admin con query param formato=prometheus
    res2 = client.get("/admin/observabilidad/metricas?formato=prometheus")
    assert res2.status_code == 200
    assert "surveys_gemini_calls_total" in res2.text
