# tests/test_copilot_mcp.py
import json
import uuid
import pytest
from unittest.mock import patch, AsyncMock

from app.models.suscriptor import Suscriptor
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.models.survey import CampanaEncuesta, PlantillaEncuesta

def setup_empresa_de_prueba(db_session):
    empresa_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    sus = db_session.query(Suscriptor).filter_by(id=empresa_id).first()
    if not sus:
        sus = Suscriptor(
            id=empresa_id,
            nombre="Empresa Test Copilot SRL",
            email="copilot_test@empresa.com",
            telefono="77123456",
            password_hash="fake_hash_123",
            rol_id=1,
            estado="activo"
        )
        db_session.add(sus)
        db_session.commit()
    return empresa_id

def test_mcp_initialize(client, db_session, empresa_headers):
    """Verifica el handshake del protocolo oficial MCP initialize."""
    setup_empresa_de_prueba(db_session)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }

    res = client.post("/mcp", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert "result" in data
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "surveys-saas-mcp-server"
    assert result["actor"]["role"] == "empresa"

def test_mcp_tools_list(client, db_session, empresa_headers):
    """Verifica que tools/list devuelva las herramientas autorizadas para la Empresa."""
    setup_empresa_de_prueba(db_session)

    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }

    res = client.post("/mcp", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert "result" in data
    tools = data["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) >= 5

    tool_names = [t["name"] for t in tools]
    assert "obtener_resumen_empresa" in tool_names
    assert "listar_campanas_empresa" in tool_names
    assert "obtener_metricas_campana" in tool_names
    assert "consultar_alertas_fraude" in tool_names
    assert "sugerir_preguntas_encuesta" in tool_names

    # Validar formato estándar MCP de las tools
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "inputSchema" in t
        assert t["inputSchema"]["type"] == "object"

def test_mcp_tools_call_resumen_empresa(client, db_session, empresa_headers):
    """Verifica la ejecución de la herramienta obtener_resumen_empresa vía MCP."""
    setup_empresa_de_prueba(db_session)

    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "obtener_resumen_empresa",
            "arguments": {}
        }
    }

    res = client.post("/mcp/rpc", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert "result" in data
    result = data["result"]
    assert result["isError"] is False
    assert len(result["content"]) > 0
    assert result["content"][0]["type"] == "text"

    content_data = json.loads(result["content"][0]["text"])
    assert "empresa_nombre" in content_data
    assert content_data["empresa_nombre"] == "Empresa Test Copilot SRL"
    assert "total_campanas" in content_data
    assert "total_plantillas" in content_data

def test_mcp_tools_call_sugerir_preguntas(client, db_session, empresa_headers):
    """Verifica la ejecución de sugerir_preguntas_encuesta vía MCP."""
    setup_empresa_de_prueba(db_session)

    payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "sugerir_preguntas_encuesta",
            "arguments": {
                "objetivo": "Medición de Clima Laboral",
                "canal": "whatsapp"
            }
        }
    }

    res = client.post("/mcp", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    result = data["result"]
    assert result["isError"] is False
    content_data = json.loads(result["content"][0]["text"])
    assert content_data["objetivo"] == "Medición de Clima Laboral"
    assert content_data["total_preguntas_sugeridas"] >= 3
    assert len(content_data["preguntas"]) >= 3

def test_mcp_tools_call_aislamiento_multitenant(client, db_session, empresa_headers):
    """Verifica que una empresa no pueda consultar métricas de una campaña que no le pertenece."""
    setup_empresa_de_prueba(db_session)

    # Campaña de otra empresa diferente
    otra_empresa_id = uuid.uuid4()
    campana_ajena = CampanaEncuesta(
        id=uuid.uuid4(),
        suscriptor_id=otra_empresa_id,
        nombre="Campaña Privada Ajena",
        canal_id=1,
        estado_id=1
    )
    db_session.add(campana_ajena)
    db_session.commit()

    payload = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "obtener_metricas_campana",
            "arguments": {
                "campana_id": str(campana_ajena.id)
            }
        }
    }

    res = client.post("/mcp", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    content_data = json.loads(data["result"]["content"][0]["text"])
    assert "error" in content_data
    assert "no pertenece a tu empresa" in content_data["error"]

def test_copilot_chat_endpoint_resumen(client, db_session, empresa_headers):
    """Verifica el endpoint /copilot/chat para la Web App del SaaS."""
    setup_empresa_de_prueba(db_session)

    payload = {
        "message": "Hola, ¿cuál es el estado y resumen de mi empresa?",
        "history": []
    }

    res = client.post("/copilot/chat", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert len(data["answer"]) > 10
    assert "tools_used" in data
    assert "suggested_actions" in data
    assert len(data["suggested_actions"]) > 0

def test_copilot_chat_alias_endpoint(client, db_session, empresa_headers):
    """Verifica el endpoint alias /agente/copilot."""
    setup_empresa_de_prueba(db_session)

    payload = {
        "message": "Recomiéndame preguntas para medir satisfacción de clientes",
        "history": []
    }

    res = client.post("/agente/copilot", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "suggested_actions" in data

def test_mcp_metodo_no_soportado(client, db_session, empresa_headers):
    """Verifica que un método no soportado en MCP retorne error estándar -32601."""
    setup_empresa_de_prueba(db_session)

    payload = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "metodo/inexistente",
        "params": {}
    }

    res = client.post("/mcp", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == -32601
