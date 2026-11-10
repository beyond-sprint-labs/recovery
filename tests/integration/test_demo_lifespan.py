import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.deps import get_paypal_gateway
from app.core.models import InvoiceRow
from app.main import create_app


def test_local_demo_startup_seeds_and_links_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYPAL_MODE", "mock")
    get_settings.cache_clear()
    get_paypal_gateway.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/v1/invoices")
            assert response.status_code == 200
            assert "INV-001" in {item["id"] for item in response.json()}
        with get_session_factory()() as session:
            invoice = session.get(InvoiceRow, "INV-001")
            assert invoice is not None
            assert invoice.paypal_invoice_id is not None
    finally:
        get_paypal_gateway.cache_clear()
