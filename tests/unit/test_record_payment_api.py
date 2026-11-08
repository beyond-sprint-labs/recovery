from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.models import CustomerRow, InvoiceRow, ProposalRow
from app.core.states import ProposalStatus
from app.main import app


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    from app.core.deps import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def executed_proposal(db_session: Session) -> str:
    now = datetime.now(UTC)

    # 1. We create the client
    customer = CustomerRow(id="CUS-001", name="Test Customer", email="test@example.com")
    db_session.add(customer)
    db_session.flush()

    # 2. We create the invoice
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

    # 3. We create the proposal
    row = ProposalRow(
        id="prop_pay_1",
        invoice_id="INV-001",
        status=ProposalStatus.EXECUTED.value,
        idempotency_key="idem-pay",
        request_hash="hash",
        customer_message="msg",
        engine_version="1.0.0",
        currency="USD",
        approved_alternative="settlement_discount",
        execution={"request_id": "req-pay", "draft_id": "MOCK-DRAFT", "new_sent": True},
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.commit()
    return "prop_pay_1"


def test_record_payment_disabled_by_default(client, executed_proposal):
    response = client.post(f"/api/v1/proposals/{executed_proposal}/sandbox/record-payment")
    assert response.status_code == 404
    assert "SANDBOX_SHORTCUT_DISABLED" in response.text
