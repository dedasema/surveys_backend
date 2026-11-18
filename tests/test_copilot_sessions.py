# tests/test_copilot_sessions.py
import json
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from app.models.suscriptor import Suscriptor
from app.models.copilot_session import CopilotSesion, CopilotMensaje

def setup_empresa_session(db_session):
    empresa_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    sus = db_session.query(Suscriptor).filter_by(id=empresa_id).first()
    if not sus:
        sus = Suscriptor(
            id=empresa_id,
            nombre="Empresa Session SRL",
            email="session_test@empresa.com",
            telefono="77123456",
            password_hash="fake_hash_123",
            rol_id=1,
            estado="activo"
        )
        db_session.add(sus)
        db_session.commit()
    return empresa_id

def test_copilot_create_and_list_sessions(client, db_session, empresa_headers):
    """Verifica crear y listar sesiones de chat del Copilot."""
    setup_empresa_session(db_session)

    # 1. Crear sesión
    create_res = client.post(
        "/copilot/sessions",
        json={"title": "Análisis de Campaña Navideña"},
        headers=empresa_headers
    )
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["title"] == "Análisis de Campaña Navideña"
    session_id = created_data["id"]

    # 2. Listar sesiones
    list_res = client.get("/copilot/sessions", headers=empresa_headers)
    assert list_res.status_code == 200
    sessions = list_res.json()
    assert isinstance(sessions, list)
    assert any(s["id"] == session_id for s in sessions)

def test_copilot_chat_with_persistence(client, db_session, empresa_headers):
    """Verifica que /copilot/chat persista el mensaje del usuario y del asistente en la sesión."""
    setup_empresa_session(db_session)

    # 1. Crear sesión vacía
    res_s = client.post("/copilot/sessions", json={"title": "Nueva conversación"}, headers=empresa_headers)
    session_id = res_s.json()["id"]

    # 2. Enviar mensaje asociándolo a la sesión
    chat_payload = {
        "message": "Hola, ¿cuántas campañas tenemos activas?",
        "session_id": session_id
    }
    chat_res = client.post("/copilot/chat", json=chat_payload, headers=empresa_headers)
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["session_id"] == session_id
    assert len(chat_data["answer"]) > 5

    # 3. Consultar mensajes de la sesión
    msg_res = client.get(f"/copilot/sessions/{session_id}/messages", headers=empresa_headers)
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) >= 2  # user + assistant

    senders = [m["sender"] for m in messages]
    assert "user" in senders
    assert "assistant" in senders

    # El mensaje del usuario debe ser el enviado
    user_msg = next(m for m in messages if m["sender"] == "user")
    assert user_msg["text"] == "Hola, ¿cuántas campañas tenemos activas?"

def test_copilot_delete_session(client, db_session, empresa_headers):
    """Verifica eliminar una sesión y sus mensajes en cascada."""
    setup_empresa_session(db_session)

    res_s = client.post("/copilot/sessions", json={"title": "Sesión a borrar"}, headers=empresa_headers)
    session_id = res_s.json()["id"]

    del_res = client.delete(f"/copilot/sessions/{session_id}", headers=empresa_headers)
    assert del_res.status_code == 204

    # Verificar que ya no exista
    get_res = client.get(f"/copilot/sessions/{session_id}/messages", headers=empresa_headers)
    assert get_res.status_code == 404

def test_mcp_rag_tool_execution(client, db_session, empresa_headers):
    """Verifica que la herramienta RAG consultar_conocimiento_rag esté disponible y ejecute en MCP."""
    setup_empresa_session(db_session)

    payload = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "consultar_conocimiento_rag",
            "arguments": {
                "pregunta": "opinión sobre la calidad del servicio",
                "top_k": 3
            }
        }
    }

    res = client.post("/mcp", json=payload, headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert "result" in data
    assert data["result"]["isError"] is False

    content_data = json.loads(data["result"]["content"][0]["text"])
    assert "pregunta" in content_data
    assert "fuentes_citadas" in content_data

def test_admin_blocked_from_copilot(client, db_session, admin_headers):
    """
    Verifica que un usuario con rol 'admin' (SuperAdmin) sea rechazado con 403 Forbidden
    tanto en /copilot/chat como en /copilot/sessions.
    """
    # 1. Probar en /copilot/chat
    chat_res = client.post("/copilot/chat", json={"message": "Hola"}, headers=admin_headers)
    assert chat_res.status_code == 403
    assert "El Copiloto Inteligente MCP está disponible exclusivamente para empresas suscriptoras." in chat_res.json()["detail"]

    # 2. Probar en /agente/copilot (alias)
    alias_res = client.post("/agente/copilot", json={"message": "Hola"}, headers=admin_headers)
    assert alias_res.status_code == 403
    assert "El Copiloto Inteligente MCP está disponible exclusivamente para empresas suscriptoras." in alias_res.json()["detail"]

    # 3. Probar en /copilot/sessions (GET)
    get_res = client.get("/copilot/sessions", headers=admin_headers)
    assert get_res.status_code == 403
    assert "El Copiloto Inteligente MCP está disponible exclusivamente para empresas suscriptoras." in get_res.json()["detail"]

    # 4. Probar en /copilot/sessions (POST)
    post_res = client.post("/copilot/sessions", json={"title": "Test"}, headers=admin_headers)
    assert post_res.status_code == 403
    assert "El Copiloto Inteligente MCP está disponible exclusivamente para empresas suscriptoras." in post_res.json()["detail"]
