"""HTTP-level tests for the customer portal (F1-13, slice 3)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.core.deps import get_execution_provider
from app.core.models import CustomerRow, InvoiceRow, ProposalRow
from app.core.states import ProposalStatus
from app.services.execution_service import ExecutionResult, ExecutionService
from app.services.recovery_service import ExecutionProvider

BASE = "/api/v1"
VIEW_KEYS = {
    "proposal_id",
    "invoice_id",
    "currency",
    "original_balance",
    "alternative",
    "customer_message",
    "expires_at",
    "status",
    "simulation_notice",
}
ALTERNATIVE_KEYS = {
    "type",
    "terms",
    "amount_due_now",
    "installment_amount",
    "total_paid",
    "schedule",
}


@pytest.fixture
def seeded(db_session: Session) -> None:
    db_session.add(CustomerRow(id="CUS-001", name="Acme Corp", email="billing@example.com"))
    db_session.flush()
    db_session.add(
        InvoiceRow(
            id="INV-001",
            customer_id="CUS-001",
            customer_name="Acme Corp",
            currency="USD",
            balance="1000.00",
            due_date="2026-10-15",
            status="OVERDUE",
            paypal_invoice_id=None,
        )
    )
    db_session.commit()


@pytest.fixture
def paypal_linked(db_session: Session, seeded: None) -> None:
    invoice = db_session.get(InvoiceRow, "INV-001")
    assert invoice is not None
    invoice.paypal_invoice_id = "INV2-ORIGINAL-0001"
    db_session.commit()


class _StubExecution:
    """Stands in for ExecutionService: records calls and returns a canned result."""

    def __init__(self, status: ProposalStatus = ProposalStatus.EXECUTED) -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def execute_replacement(self, **kwargs: Any) -> ExecutionResult:
        self.calls.append(kwargs)
        return ExecutionResult(
            status=self.status,
            new_invoice_id="MOCK-INV-0001",
            original_invoice_id=kwargs["original_invoice_id"],
            steps=("preflight_ok", "draft_created", "original_cancelled", "draft_sent"),
        )


def _install_stub(client: TestClient, stub: _StubExecution) -> None:
    def override() -> ExecutionProvider:
        return lambda: cast(ExecutionService, stub)

    client.app.dependency_overrides[get_execution_provider] = override  # type: ignore[attr-defined]


def _approved(client: TestClient, alternative: str = "settlement_discount") -> tuple[str, str]:
    created = client.post(
        f"{BASE}/invoices/INV-001/proposals",
        json={
            "customer_message": "I can pay 300 now, in 3 parts",
            "scenario_id": "S01_partial_payment_now",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    ).json()
    approved = client.post(
        f"{BASE}/proposals/{created['proposal_id']}/approve",
        json={"alternative_type": alternative, "note": None},
    )
    assert approved.status_code == 200
    body = approved.json()
    return body["proposal_id"], body["customer_link"].rstrip("/").rsplit("/", 1)[-1]


def _events(client: TestClient, proposal_id: str) -> list[dict[str, Any]]:
    response = client.get(f"{BASE}/audit-events", params={"proposal_id": proposal_id})
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _row(proposal_id: str) -> ProposalRow:
    with get_session_factory()() as session:
        row = session.get(ProposalRow, proposal_id)
        assert row is not None
        return row


def _expire(proposal_id: str) -> None:
    with get_session_factory()() as session:
        row = session.get(ProposalRow, proposal_id)
        assert row is not None
        row.customer_token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    ("alternative", "amount", "installment"),
    [("settlement_discount", "900.00", None), ("down_payment_installments", "300.00", "240.37")],
)
def test_view_exposes_only_the_approved_alternative(
    client: TestClient, alternative: str, amount: str, installment: str | None
) -> None:
    proposal_id, token = _approved(client, alternative)
    response = client.get(f"{BASE}/customer/proposals/{token}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()

    assert set(body) == VIEW_KEYS
    assert set(body["alternative"]) == ALTERNATIVE_KEYS
    assert body["alternative"]["type"] == alternative
    assert body["alternative"]["amount_due_now"] == amount
    assert body["alternative"]["installment_amount"] == installment
    assert body["original_balance"] == "1000.00"
    assert body["status"] == "PENDING_CUSTOMER"
    assert body["customer_message"] == _row(proposal_id).customer_message_final
    assert body["simulation_notice"].startswith("Simulation subject to merchant approval")
    assert ("remaining installments are simulated" in body["simulation_notice"]) is bool(
        installment
    )
    raw = response.text
    for forbidden in ("present_value", "merchant_difference_vs_balance", "policy_check"):
        assert forbidden not in raw


@pytest.mark.usefixtures("seeded")
def test_view_does_not_consume_the_token(client: TestClient) -> None:
    proposal_id, token = _approved(client)
    path = f"{BASE}/customer/proposals/{token}"
    assert client.get(path).status_code == 200
    assert client.get(path).status_code == 200
    assert _row(proposal_id).customer_token_used_at is None
    assert [event["action"] for event in _events(client, proposal_id)][-1] == (
        "CUSTOMER_LINK_ISSUED"
    )


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    "token", ["x" * 43, "short", "has space in it 123456", "dots.are.not.allowed.1234"]
)
def test_unknown_or_malformed_tokens_are_404(client: TestClient, token: str) -> None:
    for response in (
        client.get(f"{BASE}/customer/proposals/{token}"),
        client.post(f"{BASE}/customer/proposals/{token}/respond", json={"decision": "ACCEPT"}),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TOKEN_NOT_FOUND"


@pytest.mark.usefixtures("seeded")
def test_decline_is_terminal_and_never_touches_paypal(client: TestClient) -> None:
    stub = _StubExecution()
    _install_stub(client, stub)
    proposal_id, token = _approved(client)

    response = client.post(
        f"{BASE}/customer/proposals/{token}/respond", json={"decision": "DECLINE"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DECLINED"
    assert body["paypal"] is None
    (event,) = body["audit_events"]
    assert event["action"] == "CUSTOMER_DECLINED"
    assert event["actor"]["type"] == "CUSTOMER"
    assert (event["state_from"], event["state_to"]) == ("PENDING_CUSTOMER", "DECLINED")
    assert event["paypal_called"] is False
    assert stub.calls == []

    row = _row(proposal_id)
    assert row.status == "DECLINED"
    assert row.customer_token_used_at is not None
    again = client.post(f"{BASE}/customer/proposals/{token}/respond", json={"decision": "ACCEPT"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "TOKEN_ALREADY_USED"
    view = client.get(f"{BASE}/customer/proposals/{token}")
    assert view.status_code == 409
    assert view.json()["error"]["code"] == "TOKEN_ALREADY_USED"


@pytest.mark.usefixtures("paypal_linked")
@pytest.mark.parametrize(
    "outcome",
    [ProposalStatus.EXECUTED, ProposalStatus.FAILED, ProposalStatus.NEEDS_RECONCILIATION],
)
def test_accept_runs_the_execution_and_reports_the_final_state(
    client: TestClient, outcome: ProposalStatus
) -> None:
    stub = _StubExecution(outcome)
    _install_stub(client, stub)
    proposal_id, token = _approved(client)

    response = client.post(
        f"{BASE}/customer/proposals/{token}/respond", json={"decision": "ACCEPT"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == outcome.value
    assert body["paypal"] == {
        "new_invoice_id": "MOCK-INV-0001",
        "original_invoice_id": "INV2-ORIGINAL-0001",
        "steps": ["preflight_ok", "draft_created", "original_cancelled", "draft_sent"],
    }
    assert [event["action"] for event in body["audit_events"]] == [
        "CUSTOMER_ACCEPTED",
        "EXECUTION_STARTED",
    ]
    accepted, started = body["audit_events"]
    assert (accepted["state_from"], accepted["state_to"]) == ("PENDING_CUSTOMER", "ACCEPTED")
    assert (started["state_from"], started["state_to"]) == ("ACCEPTED", "EXECUTING")
    assert accepted["paypal_called"] is False

    (call,) = stub.calls
    assert call["original_invoice_id"] == "INV2-ORIGINAL-0001"
    assert call["new_amount"] == "900.00"
    assert call["recipient_email"] == "billing@example.com"
    assert call["new_invoice_number"] == f"REC-{proposal_id}"
    assert _row(proposal_id).customer_token_used_at is not None


@pytest.mark.usefixtures("paypal_linked")
def test_double_accept_executes_once(client: TestClient) -> None:
    stub = _StubExecution()
    _install_stub(client, stub)
    _, token = _approved(client)
    path = f"{BASE}/customer/proposals/{token}/respond"

    assert client.post(path, json={"decision": "ACCEPT"}).status_code == 200
    second = client.post(path, json={"decision": "ACCEPT"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "TOKEN_ALREADY_USED"
    assert len(stub.calls) == 1


@pytest.mark.usefixtures("seeded")
def test_unlinked_invoice_does_not_burn_the_token(client: TestClient) -> None:
    stub = _StubExecution()
    _install_stub(client, stub)
    proposal_id, token = _approved(client)

    response = client.post(
        f"{BASE}/customer/proposals/{token}/respond", json={"decision": "ACCEPT"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVOICE_NOT_LINKED_TO_PAYPAL"
    assert stub.calls == []

    row = _row(proposal_id)
    assert row.status == "PENDING_CUSTOMER"
    assert row.customer_token_used_at is None
    assert client.get(f"{BASE}/customer/proposals/{token}").status_code == 200
    declined = client.post(
        f"{BASE}/customer/proposals/{token}/respond", json={"decision": "DECLINE"}
    )
    assert declined.status_code == 200


@pytest.mark.usefixtures("paypal_linked")
@pytest.mark.parametrize("method", ["GET", "ACCEPT", "DECLINE"])
def test_expired_links_move_to_expired_and_answer_409(client: TestClient, method: str) -> None:
    stub = _StubExecution()
    _install_stub(client, stub)
    proposal_id, token = _approved(client)
    _expire(proposal_id)
    path = f"{BASE}/customer/proposals/{token}"

    response = (
        client.get(path)
        if method == "GET"
        else client.post(f"{path}/respond", json={"decision": method})
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"
    assert stub.calls == []

    row = _row(proposal_id)
    assert row.status == "EXPIRED"
    assert row.customer_token_used_at is None
    last = _events(client, proposal_id)[-1]
    assert last["action"] == "CUSTOMER_LINK_EXPIRED"
    assert (last["state_from"], last["state_to"]) == ("PENDING_CUSTOMER", "EXPIRED")
    assert client.get(path).json()["error"]["code"] == "TOKEN_EXPIRED"
    assert [e["action"] for e in _events(client, proposal_id)].count("CUSTOMER_LINK_EXPIRED") == 1


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    "payload", [{"decision": "MAYBE"}, {"decision": "accept"}, {}, {"decision": "ACCEPT", "x": 1}]
)
def test_invalid_respond_bodies_are_rejected_without_consuming(
    client: TestClient, payload: dict[str, Any]
) -> None:
    proposal_id, token = _approved(client)
    response = client.post(f"{BASE}/customer/proposals/{token}/respond", json=payload)
    assert response.status_code == 422
    assert _row(proposal_id).customer_token_used_at is None
