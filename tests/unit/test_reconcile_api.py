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
def proposal_in_reconciliation(db_session: Session) -> str:
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
        id="prop_recon_1",
        invoice_id="INV-001",
        status=ProposalStatus.NEEDS_RECONCILIATION.value,
        idempotency_key="idem-recon",
        request_hash="hash",
        customer_message="msg",
        engine_version="1.0.0",
        currency="USD",
        execution={"request_id": "req-recon", "draft_id": "MOCK-DRAFT"},
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.commit()
    return "prop_recon_1"


def test_reconcile_endpoint(client, proposal_in_reconciliation):
    response = client.post(f"/api/v1/proposals/{proposal_in_reconciliation}/reconcile")
    assert response.status_code in (200, 409)
    if response.status_code == 200:
        assert "status" in response.json()
