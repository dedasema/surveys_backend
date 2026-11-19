import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_cors_cloudfront_origin():
    client = TestClient(app)
    response = client.options(
        "/health",
        headers={
            "Origin": "https://dgqv4314frd93.cloudfront.net",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://dgqv4314frd93.cloudfront.net"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_desesoft_corporate_origin():
    client = TestClient(app)
    response = client.options(
        "/health",
        headers={
            "Origin": "https://desesoft.vercel.app",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://desesoft.vercel.app"
    assert response.headers.get("access-control-allow-credentials") == "true"

