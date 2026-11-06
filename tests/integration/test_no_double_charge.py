import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.paypal.gateway import NewInvoiceReq
from app.paypal.mock_gateway import MockPayPalGateway
from app.repositories.audit_repo import AuditRepo
from app.services.audit_service import AuditService
from app.services.execution_service import ExecutionService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def setup(db_session):
    gateway = MockPayPalGateway()
    audit = AuditService(AuditRepo(db_session))
    service = ExecutionService(gateway=gateway, audit=audit)
    return service, gateway


def _create_sent_invoice(gateway: MockPayPalGateway, number: str, amount: str) -> str:
    ref = gateway.create_draft(
        NewInvoiceReq(invoice_number=number, amount=amount), request_id=f"req-{number}"
    )
    gateway.send_invoice(ref.id)
    return ref.id


def test_happy_path_full_replacement(setup):
    service, gateway = setup
    original_id = _create_sent_invoice(gateway, "ORIG-HAPPY", "100.00")

    result = service.execute_replacement(
        proposal_id="prop_1",
        original_invoice_id=original_id,
        new_invoice_number="NEW-HAPPY",
        new_amount="100.00",
        request_id="req-happy",
    )
    assert result.status.value == "EXECUTED"
    assert "original_cancelled" in result.steps
    assert "draft_sent" in result.steps


def test_cancel_failure_triggers_rollback(setup):
    service, gateway = setup
    original_id = _create_sent_invoice(gateway, "ORIG-CANCEL-FAIL", "100.00")

    # Force cancel to fail
    gateway.fail_steps.add("cancel")

    result = service.execute_replacement(
        proposal_id="prop_2",
        original_invoice_id=original_id,
        new_invoice_number="NEW-CANCEL-FAIL",
        new_amount="100.00",
        request_id="req-cancel-fail",
    )
    assert result.status.value == "FAILED"
    assert "draft_deleted_after_cancel_failure" in result.steps
    assert gateway.get_invoice(original_id).status == "SENT"


def test_send_failure_after_cancel_triggers_reconciliation(setup):
    service, gateway = setup
    original_id = _create_sent_invoice(gateway, "ORIG-SEND-FAIL", "100.00")

    # Force send to fail after cancel succeeds
    gateway.fail_steps.add("send")

    result = service.execute_replacement(
        proposal_id="prop_3",
        original_invoice_id=original_id,
        new_invoice_number="NEW-SEND-FAIL",
        new_amount="100.00",
        request_id="req-send-fail",
    )
    assert result.status.value == "NEEDS_RECONCILIATION"
    assert gateway.get_invoice(original_id).status == "CANCELLED"
    assert result.new_invoice_id is not None

    # Now reconcile: remove the failure and try again
    result_reconcile = service.reconcile(
        proposal_id="prop_3",
        draft_id=result.new_invoice_id,
        original_invoice_id=original_id,
    )
    assert result_reconcile.status.value == "EXECUTED"


def test_preflight_aborts_on_partially_paid_invoice(setup):
    service, gateway = setup
    original_id = _create_sent_invoice(gateway, "ORIG-PARTIAL", "100.00")
    gateway.record_payment(original_id, "30.00")  # Now PARTIALLY_PAID

    result = service.execute_replacement(
        proposal_id="prop_4",
        original_invoice_id=original_id,
        new_invoice_number="NEW-PARTIAL",
        new_amount="100.00",
        request_id="req-partial",
    )
    assert result.status.value == "FAILED"
    assert "preflight_ok" not in result.steps
    assert gateway.get_invoice(original_id).status == "PARTIALLY_PAID"
