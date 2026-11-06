"""Unit tests for RecoveryService (F1-13 Phase A)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.core.models import InvoiceRow
from app.core.schemas import ApproveIn, CreateProposalIn, ProposalStatus, RespondIn
from app.repositories.audit_repo import AuditRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.services.audit_service import AuditService
from app.services.recovery_service import RecoveryService


@pytest.fixture
def db_session():
    # Use an in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    repo = ProposalsRepo(db_session)
    audit = AuditService(AuditRepo(db_session))
    # Using default DummyExecutionService from RecoveryService
    return RecoveryService(repo=repo, audit=audit)


@pytest.fixture
def sample_invoice(db_session):
    invoice = InvoiceRow(
        id="INV-001",
        customer_name="Test Customer",
        balance="1000.00",
        due_date="2026-10-15",
        status="OVERDUE",
    )
    db_session.add(invoice)
    db_session.commit()
    return invoice


def test_create_proposal_blocked_when_asking_40_percent(service, sample_invoice):
    body = CreateProposalIn(customer_message="I can only pay 40% of it", scenario_id="S03")
    proposal = service.create_proposal("INV-001", body, idem_key="idem-blocked-1")

    assert proposal.status == ProposalStatus.BLOCKED.value
    assert len(proposal.blocked_reasons) > 0
    assert proposal.blocked_reasons[0]["code"] == "MAX_DISCOUNT_PCT"


def test_create_proposal_idempotency(service, sample_invoice):
    body = CreateProposalIn(customer_message="I can pay 300 today")

    # First call
    proposal_1 = service.create_proposal("INV-001", body, idem_key="idem-same-key")
    # Second call with same key
    proposal_2 = service.create_proposal("INV-001", body, idem_key="idem-same-key")

    assert proposal_1.id == proposal_2.id


def test_full_happy_path(service, sample_invoice, db_session):
    # 1. Create proposal
    body = CreateProposalIn(customer_message="I can pay 300 today")
    proposal = service.create_proposal("INV-001", body, idem_key="idem-happy")
    assert proposal.status == ProposalStatus.PENDING_MERCHANT.value

    # 2. Approve proposal
    approve_body = ApproveIn(alternative_type="settlement_discount", note="Approved by merchant")
    approval_result = service.approve_proposal(proposal.id, approve_body)

    assert approval_result["proposal_id"] == proposal.id
    raw_token = approval_result["raw_token"]

    # 3. Verify state is now PENDING_CUSTOMER
    db_session.expire_all()  # <-- MAGIA: Le dice a SQLAlchemy "re-lee de la BD"
    proposal_db = service._repo.get_by_id(proposal.id)

    assert proposal_db.status == ProposalStatus.PENDING_CUSTOMER.value
    assert proposal_db.customer_token_hash is not None  # Ahora sí pasará

    # 4. Customer responds ACCEPT
    respond_body = RespondIn(decision="ACCEPT")
    response_result = service.respond_to_proposal(proposal.id, raw_token, respond_body)

    assert response_result["status"] == "EXECUTED"

    # 5. Verify final state
    db_session.expire_all()
    proposal_db = service._repo.get_by_id(proposal.id)
    assert proposal_db.status == ProposalStatus.EXECUTED.value
