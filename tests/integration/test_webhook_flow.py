"""Integration tests for the PayPal webhook flow (F1-19)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.models import CustomerRow, InvoiceRow, ProposalRow
from app.core.states import ProposalStatus
from app.main import app


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def executed_proposal(db_session: Session) -> str:
    """Seed a proposal in EXECUTED with a known draft_id."""
    now = datetime.now(UTC)

    customer = CustomerRow(id="CUS-001", name="Test Customer", email="test@example.com")
    db_session.add(customer)
    db_session.flush()

    invoice = InvoiceRow(
        id="INV-001",
        customer_id="CUS-001",
        customer_name="Test Customer",
        currency="USD",
        balance="1000.00",
        due_date="2026-10-15",
        status="OVERDUE",
    )
    db_session.add(invoice)
    db_session.flush()

    proposal = ProposalRow(
        id="prop_webhook_1",
        invoice_id="INV-001",
        status=ProposalStatus.EXECUTED.value,
        idempotency_key="idem-webhook",
        request_hash="hash",
        customer_message="msg",
        engine_version="1.0.0",
        currency="USD",
        approved_alternative="settlement_discount",
        execution={
            "request_id": "req-1",
            "draft_id": "MOCK-DRAFT-1",
            "original_cancelled": True,
            "new_sent": True,
        },
        created_at=now,
        updated_at=now,
    )
    db_session.add(proposal)
    db_session.commit()
    return "prop_webhook_1"


def test_webhook_paid_confirms_payment(client, executed_proposal):
    body = {
        "id": f"WH-{uuid4().hex}",
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"invoice": {"id": "MOCK-DRAFT-1"}},
    }
    response = client.post("/api/v1/webhooks/paypal", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["received"] is True

    # Verify the proposal moved to PAID
    from app.core.models import ProposalRow

    with next(get_db()) as session:
        proposal = session.get(ProposalRow, executed_proposal)
        assert proposal.status == ProposalStatus.PAID.value


def test_webhook_is_idempotent(client, executed_proposal):
    event_id = f"WH-{uuid4().hex}"
    body = {
        "id": event_id,
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"invoice": {"id": "MOCK-DRAFT-1"}},
    }

    # First call: should process
    response1 = client.post("/api/v1/webhooks/paypal", json=body)
    assert response1.status_code == 200

    # Second call: should be idempotent (no error, event already processed)
    response2 = client.post("/api/v1/webhooks/paypal", json=body)
    assert response2.status_code == 200
    assert response2.json()["received"] is True


def test_webhook_with_invalid_signature_is_rejected(client, monkeypatch):
    # Mock the verifier to always fail
    from app.paypal.signature import MockWebhookVerifier

    def fake_verify(self, headers, body):
        return False

    monkeypatch.setattr(MockWebhookVerifier, "verify", fake_verify)

    body = {"id": "WH-INVALID", "event_type": "INVOICING.INVOICE.PAID"}
    response = client.post("/api/v1/webhooks/paypal", json=body)
    assert response.status_code == 401
