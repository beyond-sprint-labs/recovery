from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import CustomerRow, InvoiceRow, ProposalRow
from app.core.schemas import Severity
from app.core.states import ProposalStatus
from app.repositories.execution_journal import SqlExecutionJournal
from app.services.execution_service import ExecutionAction, ExecutionSnapshot, StepRecord


@pytest.fixture
def journal(db_session: Session) -> SqlExecutionJournal:
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    return SqlExecutionJournal(factory)


@pytest.fixture
def proposal(db_session: Session) -> str:
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

    # 3. Now we create the proposal
    row = ProposalRow(
        id="prop_journal_1",
        invoice_id="INV-001",
        status=ProposalStatus.EXECUTING.value,
        idempotency_key="idem-journal",
        request_hash="hash",
        customer_message="msg",
        engine_version="1.0.0",
        currency="USD",
        paypal_called=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.commit()
    return "prop_journal_1"


def test_journal_records_step_and_transitions_status(journal, proposal, db_session):
    snapshot = ExecutionSnapshot(request_id="req-1", draft_id="MOCK-DRAFT-1")
    step = StepRecord(
        proposal_id=proposal,
        action=ExecutionAction.DRAFT_CREATED,
        severity=Severity.INFO,
        summary="Draft created",
        snapshot=snapshot,
        state_from=None,
        state_to=None,
        paypal_called=True,
    )

    journal.record(step)

    db_session.expire_all()
    row = db_session.get(ProposalRow, proposal)
    assert row.execution["draft_id"] == "MOCK-DRAFT-1"
    assert row.paypal_called is True

    loaded = journal.load(proposal)
    assert loaded is not None
    assert loaded.draft_id == "MOCK-DRAFT-1"
