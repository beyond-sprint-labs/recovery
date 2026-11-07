import pytest

from app.core.schemas import Severity
from app.core.states import ProposalStatus
from app.paypal.gateway import NewInvoiceReq, PayPalError
from app.paypal.mock_gateway import MockPayPalGateway
from app.services.execution_service import (
    ExecutionAction,
    ExecutionService,
    ExecutionSnapshot,
    StepRecord,
)

PROPOSAL_ID = "prop_1"
BUYER = "buyer@example.com"
OPEN_STATUSES = {"SENT", "UNPAID"}


class MemoryJournal:
    """In-memory ExecutionJournal: each call is its own 'transaction'; nothing is held."""

    def __init__(self) -> None:
        self.snapshots: dict[str, ExecutionSnapshot] = {}
        self.records: list[StepRecord] = []

    def load(self, proposal_id: str) -> ExecutionSnapshot | None:
        return self.snapshots.get(proposal_id)

    def record(self, step: StepRecord) -> None:
        self.records.append(step)
        self.snapshots[step.proposal_id] = step.snapshot


class CancelAppliedButTimedOutGateway(MockPayPalGateway):
    """Cancel is applied on PayPal's side but the response is lost."""

    def cancel_invoice(self, paypal_invoice_id: str) -> None:
        super().cancel_invoice(paypal_invoice_id)
        raise PayPalError("TIMEOUT", "response lost")


@pytest.fixture
def harness() -> tuple[ExecutionService, MockPayPalGateway, MemoryJournal]:
    gateway = MockPayPalGateway()
    journal = MemoryJournal()
    return ExecutionService(gateway=gateway, journal=journal), gateway, journal


def _create_sent_invoice(gateway: MockPayPalGateway, number: str, amount: str) -> str:
    ref = gateway.create_draft(
        NewInvoiceReq(invoice_number=number, amount=amount), request_id=f"req-{number}"
    )
    gateway.send_invoice(ref.id)
    return ref.id


def _args(original_id: str, number: str, request_id: str) -> dict[str, str]:
    return {
        "proposal_id": PROPOSAL_ID,
        "original_invoice_id": original_id,
        "new_invoice_number": number,
        "new_amount": "100.00",
        "recipient_email": BUYER,
        "request_id": request_id,
    }


def _open(gateway: MockPayPalGateway) -> list[str]:
    return [i["id"] for i in gateway.invoices_db.values() if i["status"] in OPEN_STATUSES]


def _by_number(gateway: MockPayPalGateway, number: str) -> list[str]:
    return [i["id"] for i in gateway.invoices_db.values() if i["req"].invoice_number == number]


def _actions(journal: MemoryJournal) -> list[ExecutionAction]:
    return [record.action for record in journal.records]


def test_happy_path_full_replacement(harness):
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-HAPPY", "100.00")

    result = service.execute_replacement(**_args(original_id, "NEW-HAPPY", "req-happy"))

    assert result.status is ProposalStatus.EXECUTED
    assert result.steps == ("preflight_ok", "draft_created", "original_cancelled", "draft_sent")
    assert gateway.get_invoice(original_id).status == "CANCELLED"
    assert _open(gateway) == [result.new_invoice_id]
    assert _actions(journal) == [
        ExecutionAction.DRAFT_CREATED,
        ExecutionAction.ORIGINAL_CANCELLED,
        ExecutionAction.INVOICE_SENT,
        ExecutionAction.COMPLETED,
    ]
    last = journal.records[-1]
    assert (last.state_from, last.state_to) == (ProposalStatus.EXECUTING, ProposalStatus.EXECUTED)


def test_cancel_failure_rolls_back_and_leaves_one_open_invoice(harness):
    """AC11: a failed cancel deletes the draft and exactly one invoice stays open."""
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-CANCEL-FAIL", "100.00")
    gateway.fail_steps.add("cancel")

    result = service.execute_replacement(**_args(original_id, "NEW-CANCEL-FAIL", "req-cf"))

    assert result.status is ProposalStatus.FAILED
    assert result.new_invoice_id is None
    assert _open(gateway) == [original_id]
    assert _by_number(gateway, "NEW-CANCEL-FAIL") == []
    assert _actions(journal) == [
        ExecutionAction.DRAFT_CREATED,
        ExecutionAction.DRAFT_DELETED,
        ExecutionAction.FAILED,
    ]
    assert journal.records[1].severity is Severity.INFO
    failed = journal.records[-1]
    assert failed.severity is Severity.CRITICAL
    assert (failed.state_from, failed.state_to) == (ProposalStatus.EXECUTING, ProposalStatus.FAILED)


def test_orphan_draft_is_audited_as_warn_when_rollback_delete_fails(harness):
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-ORPHAN", "100.00")
    gateway.fail_steps.update({"cancel", "delete"})

    result = service.execute_replacement(**_args(original_id, "NEW-ORPHAN", "req-orphan"))

    assert result.status is ProposalStatus.FAILED
    assert result.new_invoice_id is not None  # the orphan id is kept for reconcile cleanup
    assert gateway.get_invoice(result.new_invoice_id).status == "DRAFT"
    assert _open(gateway) == [original_id]
    warns = [r for r in journal.records if r.severity is Severity.WARN]
    assert len(warns) == 1
    assert warns[0].action is ExecutionAction.DRAFT_DELETED
    assert warns[0].paypal_ref == result.new_invoice_id


def test_send_failure_requires_reconciliation_then_reconcile_completes(harness):
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-SEND-FAIL", "100.00")
    gateway.fail_steps.add("send")

    result = service.execute_replacement(**_args(original_id, "NEW-SEND-FAIL", "req-sf"))

    assert result.status is ProposalStatus.NEEDS_RECONCILIATION
    assert result.new_invoice_id is not None
    assert gateway.get_invoice(original_id).status == "CANCELLED"
    assert gateway.get_invoice(result.new_invoice_id).status == "DRAFT"
    assert _open(gateway) == []
    needs = journal.records[-1]
    assert needs.action is ExecutionAction.NEEDS_RECONCILIATION
    assert needs.severity is Severity.CRITICAL
    assert needs.state_to is ProposalStatus.NEEDS_RECONCILIATION

    reconciled = service.reconcile(proposal_id=PROPOSAL_ID, original_invoice_id=original_id)

    assert reconciled.status is ProposalStatus.EXECUTED
    assert _open(gateway) == [result.new_invoice_id]
    done = journal.records[-1]
    assert done.action is ExecutionAction.RECONCILED
    assert done.source == "RECONCILIATION"
    assert (done.state_from, done.state_to) == (
        ProposalStatus.NEEDS_RECONCILIATION,
        ProposalStatus.EXECUTED,
    )


@pytest.mark.parametrize("prepare", ["draft", "cancelled", "partially_paid", "paid"])
def test_preflight_allowlist_rejects_non_cancellable_originals(harness, prepare):
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-PRE", "100.00")
    if prepare == "draft":
        original_id = gateway.create_draft(
            NewInvoiceReq(invoice_number="ORIG-DRAFT", amount="100.00"), "req-orig-draft"
        ).id
    elif prepare == "cancelled":
        gateway.cancel_invoice(original_id)
    elif prepare == "partially_paid":
        gateway.record_payment(original_id, "30.00")
    else:
        gateway.record_payment(original_id, "100.00")
    invoices_before = len(gateway.invoices_db)

    result = service.execute_replacement(**_args(original_id, "NEW-PRE", "req-pre"))

    assert result.status is ProposalStatus.FAILED
    assert "preflight_ok" not in result.steps
    assert len(gateway.invoices_db) == invoices_before
    assert _by_number(gateway, "NEW-PRE") == []
    failed = journal.records[-1]
    assert failed.action is ExecutionAction.FAILED
    assert failed.severity is Severity.CRITICAL


def test_retry_with_same_request_id_never_creates_a_second_draft(harness):
    """DoD #4: replaying the same execution reuses the persisted draft, never a new one."""
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-RETRY", "100.00")
    gateway.fail_steps.add("send")
    args = _args(original_id, "NEW-RETRY", "req-retry")

    first = service.execute_replacement(**args)
    records_after_first = len(journal.records)
    second = service.execute_replacement(**args)

    assert first.status is second.status is ProposalStatus.NEEDS_RECONCILIATION
    assert second.new_invoice_id == first.new_invoice_id
    assert len(_by_number(gateway, "NEW-RETRY")) == 1
    assert len(journal.records) == records_after_first  # the replay writes nothing
    assert gateway.get_invoice(original_id).status == "CANCELLED"

    reconciled = service.reconcile(proposal_id=PROPOSAL_ID, original_invoice_id=original_id)
    assert reconciled.status is ProposalStatus.EXECUTED
    assert _open(gateway) == [first.new_invoice_id]


def test_retry_after_completion_changes_nothing(harness):
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-DONE", "100.00")
    args = _args(original_id, "NEW-DONE", "req-done")

    first = service.execute_replacement(**args)
    records_after_first = len(journal.records)
    second = service.execute_replacement(**args)

    assert first.status is second.status is ProposalStatus.EXECUTED
    assert second.new_invoice_id == first.new_invoice_id
    assert len(_by_number(gateway, "NEW-DONE")) == 1
    assert len(journal.records) == records_after_first
    assert _open(gateway) == [first.new_invoice_id]


def test_crash_after_draft_persisted_resumes_without_creating_another(harness):
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-RESUME", "100.00")
    draft = gateway.create_draft(
        NewInvoiceReq(invoice_number="NEW-RESUME", amount="100.00", recipient_email=BUYER),
        "req-resume",
    )
    journal.snapshots[PROPOSAL_ID] = ExecutionSnapshot(request_id="req-resume", draft_id=draft.id)

    result = service.execute_replacement(**_args(original_id, "NEW-RESUME", "req-resume"))

    assert result.status is ProposalStatus.EXECUTED
    assert result.new_invoice_id == draft.id
    assert _by_number(gateway, "NEW-RESUME") == [draft.id]
    assert _open(gateway) == [draft.id]


def test_cancel_applied_but_response_lost_still_sends_the_replacement():
    """A timeout must not be read as 'cancel failed': deleting the draft would leave the
    debtor with no payable invoice."""
    gateway = CancelAppliedButTimedOutGateway()
    journal = MemoryJournal()
    service = ExecutionService(gateway=gateway, journal=journal)
    original_id = _create_sent_invoice(gateway, "ORIG-LOST", "100.00")

    result = service.execute_replacement(**_args(original_id, "NEW-LOST", "req-lost"))

    assert result.status is ProposalStatus.EXECUTED
    assert _open(gateway) == [result.new_invoice_id]
    assert ExecutionAction.DRAFT_DELETED not in _actions(journal)


def test_reconcile_never_sends_while_the_original_is_open(harness):
    service, gateway, journal = harness
    original_id = _create_sent_invoice(gateway, "ORIG-OPEN", "100.00")
    draft = gateway.create_draft(
        NewInvoiceReq(invoice_number="NEW-OPEN", amount="100.00", recipient_email=BUYER),
        "req-open",
    )
    journal.snapshots[PROPOSAL_ID] = ExecutionSnapshot(request_id="req-open", draft_id=draft.id)

    result = service.reconcile(proposal_id=PROPOSAL_ID, original_invoice_id=original_id)

    assert result.status is ProposalStatus.FAILED
    assert _open(gateway) == [original_id]
    assert _by_number(gateway, "NEW-OPEN") == []
    assert journal.records
    assert all(record.source == "RECONCILIATION" for record in journal.records)
