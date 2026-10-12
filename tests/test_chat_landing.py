# tests/test_chat_landing.py
from unittest.mock import patch, AsyncMock

def test_chat_landing_public_access_no_auth(client):
    """Verifica que el endpoint es 100% público y responde sin cabeceras Authorization."""
    payload = {
        "message": "¿Qué planes tienen?",
        "history": []
    }
    res = client.post("/chat/landing", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert "actions" in data
    assert isinstance(data["actions"], list)
    assert len(data["actions"]) > 0
    # Al preguntar por planes debe incluir acción a precios o registro
    hrefs = [a.get("href") for a in data["actions"]]
    assert any(h in ["#precios", "/register"] for h in hrefs)

def test_chat_publico_alias_endpoint(client):
    """Verifica que el alias /chat/publico funcione idénticamente."""
    payload = {
        "message": "Hola, ¿cómo funciona el audio con IA?",
        "history": [
            {"sender": "user", "text": "Hola"},
            {"sender": "bot", "text": "¡Hola! ¿En qué puedo ayudarte?"}
        ]
    }
    res = client.post("/chat/publico", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "actions" in data
    assert isinstance(data["actions"], list)

def test_chat_landing_empty_message_validation(client):
    """Verifica que mensajes vacíos retornen error 400."""
    res = client.post("/chat/landing", json={"message": "   "})
    assert res.status_code == 400
    assert "Mensaje vacío" in res.json().get("detail", "")

def test_chat_landing_with_mocked_llm(client):
    """Verifica el flujo cuando un proveedor LLM devuelve una respuesta completa."""
    mock_llm_answer = (
        "SurveySaaS soporta recolección por voz y audio con IA usando modelos Whisper.\n"
        "Podés probarlo creando tu cuenta gratis en /register o ver los precios en #precios."
    )
    with patch("app.services.chat_landing_service._call_gemini_landing", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_llm_answer

        res = client.post(
            "/chat/landing",
            json={
                "message": "¿Tienen soporte de audio?",
                "history": []
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == mock_llm_answer
        hrefs = [a["href"] for a in data["actions"]]
        assert "/register" in hrefs
        assert "#precios" in hrefs
