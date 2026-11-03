"""Tests for CORS and preflight handling, specifically for Idempotency-Key."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_preflight_allowed_origin() -> None:
    """OPTIONS request from allowed origin with Idempotency-Key must succeed."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type, Idempotency-Key",
    }
    response = client.options("/api/v1/invoices/INV-001/proposals", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "idempotency-key" in response.headers.get("access-control-allow-headers", "").lower()


def test_cors_preflight_unauthorized_origin() -> None:
    """OPTIONS request from an untrusted origin must not be allowed."""
    headers = {
        "Origin": "https://malicious-site.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type, Idempotency-Key",
    }
    response = client.options("/api/v1/invoices/INV-001/proposals", headers=headers)
    assert response.headers.get("access-control-allow-origin") is None