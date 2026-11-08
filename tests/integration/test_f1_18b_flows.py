"""F1-18b integration tests: reconcile, orphan cleanup, Sandbox shortcut, lazy reconciliation,
the real alternatives and the outbound transaction guard (invariant 5)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.agent.mock_agent import ScriptedAgent
from app.core.config import get_settings
from app.core.db import get_engine, get_session_factory
from app.core.deps import get_paypal_gateway
from app.core.models import InvoiceRow, ProposalRow
from app.core.states import ProposalStatus
from app.paypal.gateway import NewInvoiceReq, PayPalError, PayPalInvoiceRef, PayPalInvoiceState
from app.paypal.mock_gateway import MockPayPalGateway
from app.repositories.audit_repo import AuditRepo
from app.repositories.execution_journal import SqlExecutionJournal
from app.repositories.invoices_repo import InvoicesRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.repositories.unit_of_work import SqlAlchemyUnitOfWork
from app.seed.loader import seed_database
from app.services.audit_service import AuditService
from app.services.execution_service import ExecutionService
from app.services.recovery_service import AgentBinding, RecoveryService

API = "/api/v1"
SCENARIO_ID = "S01_partial_payment_now"
BUYER = "northwind@example.com"
SETTLEMENT = "settlement_discount"
INSTALLMENTS = "down_payment_installments"
OPEN_STATUSES = {"SENT", "UNPAID"}


# --- fixtures and helpers ---------------------------------------------------------------


@pytest.fixture
def gateway() -> Iterator[MockPayPalGateway]:
    get_paypal_gateway.cache_clear()
    instance = get_paypal_gateway()
    assert isinstance(instance, MockPayPalGateway)
    yield instance
    get_paypal_gateway.cache_clear()


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    with get_session_factory().begin() as session:
        seed_database(session)
    return client


@pytest.fixture
def sandbox_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ALLOW_SANDBOX_PAYMENT_SHORTCUT", "true")
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        with get_session_factory().begin() as session:
            seed_database(session)
        yield test_client


def _create_proposal(client: TestClient) -> dict[str, Any]:
    response = client.post(
        f"{API}/invoices/INV-001/proposals",
        headers={"Idempotency-Key": uuid4().hex},
        json={"customer_message": "I can pay part of it now.", "scenario_id": SCENARIO_ID},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PENDING_MERCHANT", body
    return body


def _force_state(
    proposal_id: str,
    status: ProposalStatus,
    *,
    approved: str = SETTLEMENT,
    execution: dict[str, Any] | None = None,
    last_check: datetime | None = None,
) -> None:
    """Move a proposal to a later state; the approve/respond slices do not exist yet."""
    with get_session_factory().begin() as session:
        session.execute(
            update(ProposalRow)
            .where(ProposalRow.id == proposal_id)
            .values(
                status=status.value,
                approved_alternative=approved,
                execution=execution,
                last_paypal_check_at=last_check,
                paypal_called=execution is not None,
            )
        )


def _state(proposal_id: str) -> tuple[str, dict[str, Any] | None]:
    with get_session_factory()() as session:
        row = session.get(ProposalRow, proposal_id)
        assert row is not None
        return row.status, row.execution


def _amount(body: dict[str, Any], approved: str) -> str:
    alternative = next(item for item in body["alternatives"] if item["type"] == approved)
    return str(alternative["amount_due_now"])


def _sent_execution(draft_id: str) -> dict[str, Any]:
    return {
        "request_id": "req-test",
        "draft_id": draft_id,
        "original_cancelled": True,
        "new_sent": True,
    }


def _ago(seconds: int) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=seconds)


def _link_original(gateway: MockPayPalGateway, *, cancelled: bool = False) -> str:
    """Create INV-001's original invoice in PayPal and link it to the seeded invoice."""
    ref = gateway.create_draft(
        NewInvoiceReq(invoice_number="INV-001", amount="1000.00", recipient_email=BUYER),
        "req-original",
    )
    gateway.send_invoice(ref.id)
    if cancelled:
        gateway.cancel_invoice(ref.id)
    with get_session_factory().begin() as session:
        row = session.get(InvoiceRow, "INV-001")
        assert row is not None
        row.paypal_invoice_id = ref.id
    return ref.id


def _new_invoice(gateway: MockPayPalGateway, number: str, amount: str, *, sent: bool) -> str:
    ref = gateway.create_draft(
        NewInvoiceReq(invoice_number=number, amount=amount, recipient_email=BUYER), f"req-{number}"
    )
    if sent:
        gateway.send_invoice(ref.id)
    return ref.id


def _open_ids(gateway: MockPayPalGateway) -> list[str]:
    return [item["id"] for item in gateway.invoices_db.values() if item["status"] in OPEN_STATUSES]


def _recovery_service(session: Session, gateway: MockPayPalGateway) -> RecoveryService:
    journal_sessions = sessionmaker(
        bind=session.get_bind(), autoflush=False, expire_on_commit=False
    )
    return RecoveryService(
        invoices=InvoicesRepo(session),
        proposals=ProposalsRepo(session),
        audit=AuditService(AuditRepo(session)),
        uow=SqlAlchemyUnitOfWork(session),
        agent_factory=lambda scenario_id: AgentBinding(
            agent=ScriptedAgent(scenario_id), mode="DEMO"
        ),
        settings=get_settings(),
        execution_provider=lambda: ExecutionService(gateway, SqlExecutionJournal(journal_sessions)),
    )


# --- reconcile and orphan cleanup -----------------------------------------------------------


def test_reconcile_sends_the_pending_draft_and_reaches_executed(seeded, gateway):
    _link_original(gateway, cancelled=True)
    draft_id = _new_invoice(gateway, "REC-RECON-1", "900.00", sent=False)
    proposal = _create_proposal(seeded)
    pid = proposal["proposal_id"]
    _force_state(
        pid,
        ProposalStatus.NEEDS_RECONCILIATION,
        execution={
            "request_id": "req-1",
            "draft_id": draft_id,
            "original_cancelled": True,
            "new_sent": False,
        },
    )

    response = seeded.post(f"{API}/proposals/{pid}/reconcile")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "EXECUTED"
    [event] = body["audit_events"]
    assert (event["action"], event["source"]) == ("RECONCILED", "RECONCILIATION")
    assert (event["state_from"], event["state_to"]) == ("NEEDS_RECONCILIATION", "EXECUTED")
    assert gateway.get_invoice(draft_id).status == "SENT"
    assert _open_ids(gateway) == [draft_id]
    status, execution = _state(pid)
    assert status == "EXECUTED"
    assert execution is not None and execution["new_sent"] is True


def test_reconcile_discards_the_draft_when_the_original_is_still_open(seeded, gateway):
    original_id = _link_original(gateway)
    draft_id = _new_invoice(gateway, "REC-RECON-2", "900.00", sent=False)
    pid = _create_proposal(seeded)["proposal_id"]
    _force_state(
        pid,
        ProposalStatus.NEEDS_RECONCILIATION,
        execution={
            "request_id": "req-2",
            "draft_id": draft_id,
            "original_cancelled": False,
            "new_sent": False,
        },
    )

    response = seeded.post(f"{API}/proposals/{pid}/reconcile")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert [event["action"] for event in body["audit_events"]] == [
        "PAYPAL_DRAFT_DELETED",
        "EXECUTION_FAILED",
    ]
    assert {event["source"] for event in body["audit_events"]} == {"RECONCILIATION"}
    assert draft_id not in gateway.invoices_db
    assert _open_ids(gateway) == [original_id]


def test_reconcile_cleans_the_orphan_draft_of_a_failed_proposal(seeded, gateway):
    _link_original(gateway)
    draft_id = _new_invoice(gateway, "REC-ORPHAN", "900.00", sent=False)
    pid = _create_proposal(seeded)["proposal_id"]
    _force_state(
        pid,
        ProposalStatus.FAILED,
        execution={
            "request_id": "req-3",
            "draft_id": draft_id,
            "original_cancelled": False,
            "new_sent": False,
        },
    )
    path = f"{API}/proposals/{pid}/reconcile"

    response = seeded.post(path)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    [event] = body["audit_events"]
    assert (event["action"], event["severity"], event["source"]) == (
        "PAYPAL_DRAFT_DELETED",
        "INFO",
        "RECONCILIATION",
    )
    assert draft_id not in gateway.invoices_db
    again = seeded.post(path)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PROPOSAL_NOT_RECONCILABLE"


# --- real execution with both alternatives ---------------------------------------------------


@pytest.mark.parametrize("approved", [SETTLEMENT, INSTALLMENTS])
def test_run_execution_replaces_the_invoice_for_each_alternative(seeded, gateway, approved):
    original_id = _link_original(gateway)
    body = _create_proposal(seeded)
    pid = body["proposal_id"]
    expected = _amount(body, approved)
    _force_state(pid, ProposalStatus.EXECUTING, approved=approved)

    with get_session_factory()() as session:
        result = _recovery_service(session, gateway).run_execution(pid)

    assert result.status is ProposalStatus.EXECUTED
    new_id = result.new_invoice_id
    assert new_id is not None
    assert _open_ids(gateway) == [new_id]  # AC11: exactly one open invoice
    assert gateway.get_invoice(original_id).status == "CANCELLED"
    assert gateway.get_invoice(new_id).total_amount == expected
    assert gateway.invoices_db[new_id]["req"].invoice_number == f"REC-{pid}"
    status, execution = _state(pid)
    assert status == "EXECUTED"
    assert execution is not None and execution["new_sent"] is True


# --- Sandbox payment shortcut ----------------------------------------------------------------


def test_sandbox_payment_uses_the_server_amount_and_confirms_payment(sandbox_client, gateway):
    body = _create_proposal(sandbox_client)
    pid = body["proposal_id"]
    amount = _amount(body, SETTLEMENT)
    invoice_id = _new_invoice(gateway, "REC-PAY-1", amount, sent=True)
    _force_state(pid, ProposalStatus.EXECUTED, execution=_sent_execution(invoice_id))
    path = f"{API}/proposals/{pid}/sandbox/record-payment"

    response = sandbox_client.post(path, json={"amount": "0.01"})  # a smuggled amount is ignored

    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "PAID"
    [event] = out["audit_events"]
    assert event["action"] == "PAYMENT_CONFIRMED"
    assert event["actor"]["type"] == "PAYPAL"
    assert event["source"] == "RECONCILIATION"
    assert event["paypal_ref"] == invoice_id
    assert "Merchant-recorded payment (Sandbox)" in event["summary"]
    assert gateway.invoices_db[invoice_id]["paid_amount"] == Decimal(amount)
    again = sandbox_client.post(path)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PROPOSAL_NOT_EXECUTED"


def test_sandbox_payment_requires_an_executed_proposal(sandbox_client, gateway):
    pid = _create_proposal(sandbox_client)["proposal_id"]

    response = sandbox_client.post(f"{API}/proposals/{pid}/sandbox/record-payment")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_EXECUTED"


def test_sandbox_shortcut_is_closed_for_a_live_paypal_url(monkeypatch):
    monkeypatch.setenv("ALLOW_SANDBOX_PAYMENT_SHORTCUT", "true")
    monkeypatch.setenv("PAYPAL_BASE_URL", "https://api-m.paypal.com")
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as live_client:
        response = live_client.post(f"{API}/proposals/prop_000000000000/sandbox/record-payment")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SANDBOX_SHORTCUT_DISABLED"


# --- lazy reconciliation ---------------------------------------------------------------------


def test_get_proposal_confirms_a_paid_invoice_lazily(seeded, gateway):
    body = _create_proposal(seeded)
    pid = body["proposal_id"]
    amount = _amount(body, SETTLEMENT)
    invoice_id = _new_invoice(gateway, "REC-LAZY-1", amount, sent=True)
    gateway.record_payment(invoice_id, amount)
    _force_state(
        pid, ProposalStatus.EXECUTED, execution=_sent_execution(invoice_id), last_check=_ago(60)
    )

    first = seeded.get(f"{API}/proposals/{pid}")

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PAID"
    assert first.json()["audit_event"]["action"] == "PAYMENT_CONFIRMED"
    assert seeded.get(f"{API}/proposals/{pid}").json()["status"] == "PAID"
    feed = seeded.get(f"{API}/audit-events", params={"proposal_id": pid, "limit": 100})
    actions = [item["action"] for item in feed.json()["items"]]
    assert actions.count("PAYMENT_CONFIRMED") == 1


def test_get_proposal_ignores_a_partial_payment(seeded, gateway):
    body = _create_proposal(seeded)
    pid = body["proposal_id"]
    amount = _amount(body, SETTLEMENT)
    invoice_id = _new_invoice(gateway, "REC-LAZY-2", amount, sent=True)
    gateway.record_payment(invoice_id, "100.00")
    _force_state(
        pid, ProposalStatus.EXECUTED, execution=_sent_execution(invoice_id), last_check=_ago(60)
    )

    response = seeded.get(f"{API}/proposals/{pid}")

    assert response.status_code == 200
    assert response.json()["status"] == "EXECUTED"


def test_get_proposal_does_not_call_paypal_when_checked_recently(seeded, gateway, monkeypatch):
    body = _create_proposal(seeded)
    pid = body["proposal_id"]
    invoice_id = _new_invoice(gateway, "REC-LAZY-3", _amount(body, SETTLEMENT), sent=True)
    _force_state(
        pid, ProposalStatus.EXECUTED, execution=_sent_execution(invoice_id), last_check=_ago(2)
    )

    def forbidden(_invoice_id: str) -> PayPalInvoiceState:
        raise AssertionError("PayPal must not be called within the 10 s throttle")

    monkeypatch.setattr(gateway, "get_invoice", forbidden)

    response = seeded.get(f"{API}/proposals/{pid}")

    assert response.status_code == 200
    assert response.json()["status"] == "EXECUTED"


def test_lazy_reconciliation_survives_paypal_errors_and_throttles(seeded, gateway, monkeypatch):
    body = _create_proposal(seeded)
    pid = body["proposal_id"]
    invoice_id = _new_invoice(gateway, "REC-LAZY-4", _amount(body, SETTLEMENT), sent=True)
    _force_state(
        pid, ProposalStatus.EXECUTED, execution=_sent_execution(invoice_id), last_check=_ago(60)
    )
    calls: list[str] = []

    def flaky(invoice: str) -> PayPalInvoiceState:
        calls.append(invoice)
        raise PayPalError("TIMEOUT", "PayPal did not answer in time")

    monkeypatch.setattr(gateway, "get_invoice", flaky)

    assert seeded.get(f"{API}/proposals/{pid}").json()["status"] == "EXECUTED"
    assert seeded.get(f"{API}/proposals/{pid}").json()["status"] == "EXECUTED"
    assert len(calls) == 1  # the failed check still counts for the throttle


# --- invariant 5: no open database transaction during a PayPal call ------------------------


class _SpyGateway(MockPayPalGateway):
    """Fails the test if any tracked session has an open transaction during a PayPal call."""

    def __init__(self, sessions: list[Session]) -> None:
        super().__init__()
        self._sessions = sessions
        self.calls: list[str] = []

    def _spy(self, name: str) -> None:
        self.calls.append(name)
        open_sessions = [session for session in self._sessions if session.in_transaction()]
        assert not open_sessions, f"{name}: a database transaction was open during the PayPal call"

    def create_draft(self, req: NewInvoiceReq, request_id: str) -> PayPalInvoiceRef:
        self._spy("create_draft")
        return super().create_draft(req, request_id)

    def cancel_invoice(self, paypal_invoice_id: str) -> None:
        self._spy("cancel_invoice")
        super().cancel_invoice(paypal_invoice_id)

    def send_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceRef:
        self._spy("send_invoice")
        return super().send_invoice(paypal_invoice_id)

    def delete_draft(self, paypal_invoice_id: str) -> None:
        self._spy("delete_draft")
        super().delete_draft(paypal_invoice_id)

    def get_invoice(self, paypal_invoice_id: str) -> PayPalInvoiceState:
        self._spy("get_invoice")
        return super().get_invoice(paypal_invoice_id)

    def record_payment(self, paypal_invoice_id: str, amount: str) -> None:
        self._spy("record_payment")
        super().record_payment(paypal_invoice_id, amount)


def _tracking_factory(sessions: list[Session]) -> sessionmaker[Any]:
    class TrackedSession(Session):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            sessions.append(self)

    return sessionmaker(
        bind=get_engine(), class_=TrackedSession, autoflush=False, expire_on_commit=False
    )


def test_no_database_transaction_is_open_during_any_paypal_call(seeded):
    sessions: list[Session] = []
    gateway = _SpyGateway(sessions)
    original_id = _link_original(gateway)
    body = _create_proposal(seeded)
    pid = body["proposal_id"]
    _force_state(pid, ProposalStatus.EXECUTING)
    service = ExecutionService(gateway, SqlExecutionJournal(_tracking_factory(sessions)))
    gateway.fail_steps.add("send")  # the first run ends in NEEDS_RECONCILIATION

    first = service.execute_replacement(
        proposal_id=pid,
        original_invoice_id=original_id,
        new_invoice_number=f"REC-{pid}",
        new_amount=_amount(body, SETTLEMENT),
        recipient_email=BUYER,
        request_id="req-guard",
    )
    assert first.status is ProposalStatus.NEEDS_RECONCILIATION
    second = service.reconcile(proposal_id=pid, original_invoice_id=original_id)

    assert second.status is ProposalStatus.EXECUTED
    assert {"get_invoice", "create_draft", "cancel_invoice", "send_invoice"} <= set(gateway.calls)
    assert sessions, "the journal must have used the tracked sessions"
    assert not any(session.in_transaction() for session in sessions)
