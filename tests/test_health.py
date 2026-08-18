# tests/test_health.py
def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_stripe_fallback_endpoint(client):
    response = client.get("/stripe-verify-session?session_id=test_123")
    assert response.status_code == 200
    assert response.json()["success"] is True
