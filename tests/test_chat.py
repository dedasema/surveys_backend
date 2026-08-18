from unittest.mock import patch, AsyncMock

def test_chat_endpoint_structure(client, empresa_headers):
    # Mocking gemini response to test route isolation and safety
    with patch("app.routers.chat_router.chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "answer": "Hola, puedes crear una plantilla desde la sección Plantillas.",
            "action_log": []
        }
        res = client.post(
            "/chat",
            json={"message": "¿Cómo creo una plantilla?", "context": {"route": "/dashboard-suscriptor/plantillas"}},
            headers=empresa_headers
        )
        assert res.status_code == 200
        data = res.json()
        assert "answer" in data
        assert "action_log" in data
