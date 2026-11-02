from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.schemas import CreateProposalIn


def test_health_reports_modes(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "demo_mode": True,
        "engine_version": "1.0.0",
        "paypal_mode": "mock",
        "agent_mode": "scripted",
    }


def test_preflight_allows_idempotency_key_from_configured_origin(
    client: TestClient, allowed_origin: str
) -> None:
    response = client.options(
        "/api/v1/invoices/INV-001/proposals",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "idempotency-key, content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == allowed_origin
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-max-age"] == "600"


def test_preflight_rejects_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/invoices/INV-001/proposals",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "idempotency-key",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_preflight_rejects_headers_that_are_not_whitelisted(
    client: TestClient, allowed_origin: str
) -> None:
    response = client.options(
        "/api/v1/invoices/INV-001/proposals",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-policy-override",
        },
    )

    assert response.status_code == 400


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "HTTP_404", "message": "Not Found"}}


def test_policy_field_in_request_body_returns_422_with_envelope(client: TestClient) -> None:
    app: FastAPI = client.app  # type: ignore[assignment]

    class Echo(BaseModel):
        ok: bool

    @app.post("/_test/proposals", response_model=Echo)
    def create(body: CreateProposalIn) -> Echo:
        return Echo(ok=True)

    response = client.post(
        "/_test/proposals",
        json={"customer_message": "Can I get 40% off?", "policy": {"max_discount_pct": "100"}},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "policy" in body["error"]["message"]