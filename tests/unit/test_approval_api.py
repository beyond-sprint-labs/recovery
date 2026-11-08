"""HTTP-level tests for merchant approval and rejection (F1-13, slice 2)."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.models import CustomerRow, InvoiceRow, ProposalRow

BASE = "/api/v1"


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


def _create(
    client: TestClient,
    scenario: str = "S01_partial_payment_now",
    message: str = "I can pay 300 now, in 3 parts",
) -> dict[str, Any]:
    response = client.post(
        f"{BASE}/invoices/INV-001/proposals",
        json={"customer_message": message, "scenario_id": scenario},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _approve(
    client: TestClient,
    proposal_id: str,
    alternative: str = "settlement_discount",
    note: str | None = None,
) -> Any:
    return client.post(
        f"{BASE}/proposals/{proposal_id}/approve",
        json={"alternative_type": alternative, "note": note},
    )


def _events(client: TestClient, proposal_id: str) -> list[dict[str, Any]]:
    response = client.get(f"{BASE}/audit-events", params={"proposal_id": proposal_id})
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _row(proposal_id: str) -> ProposalRow:
    with get_session_factory()() as session:
        row = session.get(ProposalRow, proposal_id)
        assert row is not None
        return row


@pytest.mark.usefixtures("seeded")
def test_approve_settlement_issues_a_single_use_link(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://recovery.example.test/")
    get_settings.cache_clear()
    proposal = _create(client)
    proposal_id = proposal["proposal_id"]

    response = _approve(client, proposal_id, note="Long-standing customer")
    assert response.status_code == 200
    body = response.json()

    assert body["proposal_id"] == proposal_id
    assert body["status"] == "PENDING_CUSTOMER"
    assert body["approved_alternative"] == "settlement_discount"
    prefix = "https://recovery.example.test/customer/"
    assert body["customer_link"].startswith(prefix)
    token = body["customer_link"][len(prefix) :]
    assert len(token) >= 43  # token_urlsafe(32)

    first, second = body["audit_events"]
    assert (first["action"], first["state_from"], first["state_to"]) == (
        "PROPOSAL_APPROVED",
        "PENDING_MERCHANT",
        "APPROVED",
    )
    assert first["actor"] == {"type": "MERCHANT", "id": "merchant_demo", "mode": None}
    assert "Long-standing customer" in first["summary"]
    assert (second["action"], second["state_from"], second["state_to"]) == (
        "CUSTOMER_LINK_ISSUED",
        "APPROVED",
        "PENDING_CUSTOMER",
    )
    assert second["summary"] == "Single-use customer link issued; expires in 24 hours"
    assert first["paypal_called"] is False
    assert second["paypal_called"] is False

    expires = datetime.fromisoformat(body["customer_token_expires_at"])
    issued = datetime.fromisoformat(second["ts"])
    assert abs((expires - issued) - timedelta(minutes=1440)) <= timedelta(seconds=2)

    row = _row(proposal_id)
    assert row.status == "PENDING_CUSTOMER"
    assert row.approved_alternative == "settlement_discount"
    assert row.customer_token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert row.customer_message_final == (
        "Hello, your proposed settlement terms for invoice INV-001 have been approved. "
        "You can settle the full balance today with a single payment of $900.00 "
        "(10% discount). Please review the terms and confirm below."
    )
    assert token not in json.dumps(_events(client, proposal_id))
    assert token not in (row.customer_message_final or "")

    fetched = client.get(f"{BASE}/proposals/{proposal_id}").json()
    assert fetched["status"] == "PENDING_CUSTOMER"
    assert fetched["approved_alternative"] == "settlement_discount"
    assert fetched["paypal_called"] is False


@pytest.mark.usefixtures("seeded")
def test_approve_installments_uses_the_installment_template(client: TestClient) -> None:
    proposal = _create(client)
    response = _approve(client, proposal["proposal_id"], "down_payment_installments")
    assert response.status_code == 200
    assert response.json()["approved_alternative"] == "down_payment_installments"
    assert _row(proposal["proposal_id"]).customer_message_final == (
        "Hello, your proposed installment arrangement for invoice INV-001 has been approved: "
        "pay $300.00 today, followed by 3 monthly payments of $240.37, for a total of "
        "$1021.10. Please review the schedule and confirm below."
    )


@pytest.mark.usefixtures("seeded")
def test_a_second_approve_conflicts_and_issues_no_second_link(client: TestClient) -> None:
    proposal_id = _create(client)["proposal_id"]
    assert _approve(client, proposal_id).status_code == 200
    again = _approve(client, proposal_id, "down_payment_installments")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PROPOSAL_NOT_PENDING_MERCHANT"
    actions = [event["action"] for event in _events(client, proposal_id)]
    assert actions == ["PROPOSAL_DRAFTED", "PROPOSAL_APPROVED", "CUSTOMER_LINK_ISSUED"]


@pytest.mark.usefixtures("seeded")
def test_blocked_proposals_cannot_be_approved_or_rejected(client: TestClient) -> None:
    blocked = _create(client, "S03_exceeds_discount", "Can I get 40% off?")
    assert blocked["status"] == "BLOCKED"
    approve = _approve(client, blocked["proposal_id"])
    assert approve.status_code == 409
    assert approve.json()["error"]["code"] == "PROPOSAL_NOT_PENDING_MERCHANT"
    reject = client.post(f"{BASE}/proposals/{blocked['proposal_id']}/reject", json={})
    assert reject.status_code == 409
    assert _row(blocked["proposal_id"]).customer_token_hash is None


@pytest.mark.usefixtures("seeded")
def test_policy_tightened_after_drafting_makes_the_alternative_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_id = _create(client)["proposal_id"]
    monkeypatch.setenv("POLICY_MAX_DISCOUNT_PCT", "5")
    get_settings.cache_clear()

    response = _approve(client, proposal_id)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ALTERNATIVE_NOT_OFFERED"
    assert client.get(f"{BASE}/proposals/{proposal_id}").json()["status"] == "PENDING_MERCHANT"
    assert _row(proposal_id).customer_token_hash is None

    # The installment alternative still complies with the stricter policy.
    assert _approve(client, proposal_id, "down_payment_installments").status_code == 200


@pytest.mark.usefixtures("seeded")
def test_tampered_final_message_blocks_the_proposal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_id = _create(client)["proposal_id"]
    monkeypatch.setattr(
        "app.services.recovery_service.render_customer_message",
        lambda **_: "Hello, please pay $850.00 today for invoice INV-001.",
    )

    response = _approve(client, proposal_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TEXT_NUMBER_MISMATCH"

    fetched = client.get(f"{BASE}/proposals/{proposal_id}").json()
    assert fetched["status"] == "BLOCKED"
    assert fetched["blocked_reasons"][0]["code"] == "TEXT_NUMBER_MISMATCH"
    assert fetched["text_number_check"]["status"] == "FAILED"
    assert "850.00" in fetched["text_number_check"]["unmatched"]
    assert fetched["paypal_called"] is False

    last = _events(client, proposal_id)[-1]
    assert last["action"] == "PROPOSAL_BLOCKED"
    assert last["severity"] == "CRITICAL"
    assert (last["state_from"], last["state_to"]) == ("PENDING_MERCHANT", "BLOCKED")
    assert last["actor"]["id"] == "text_guard"
    assert _row(proposal_id).customer_token_hash is None

    retry = _approve(client, proposal_id)
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "PROPOSAL_NOT_PENDING_MERCHANT"


@pytest.mark.usefixtures("seeded")
def test_reject_moves_to_rejected_and_audits_the_note(client: TestClient) -> None:
    proposal_id = _create(client)["proposal_id"]
    response = client.post(
        f"{BASE}/proposals/{proposal_id}/reject", json={"note": "Customer history is poor"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    (event,) = body["audit_events"]
    assert event["action"] == "PROPOSAL_REJECTED"
    assert (event["state_from"], event["state_to"]) == ("PENDING_MERCHANT", "REJECTED")
    assert "Customer history is poor" in event["summary"]
    assert event["paypal_called"] is False

    assert _approve(client, proposal_id).status_code == 409
    again = client.post(f"{BASE}/proposals/{proposal_id}/reject", json={})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PROPOSAL_NOT_PENDING_MERCHANT"


@pytest.mark.usefixtures("seeded")
def test_hidden_characters_in_notes_never_reach_the_audit_trail(client: TestClient) -> None:
    proposal_id = _create(client)["proposal_id"]
    response = client.post(
        f"{BASE}/proposals/{proposal_id}/reject", json={"note": "fine\u200b note"}
    )
    summary = response.json()["audit_events"][0]["summary"]
    assert "\u200b" not in summary
    assert "fine note" in summary


@pytest.mark.usefixtures("seeded")
def test_unknown_proposals_are_404(client: TestClient) -> None:
    approve = _approve(client, "prop_missing")
    assert approve.status_code == 404
    assert approve.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"
    reject = client.post(f"{BASE}/proposals/prop_missing/reject", json={})
    assert reject.status_code == 404


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    "payload",
    [
        {"alternative_type": "not_a_type"},
        {"alternative_type": "settlement_discount", "policy": {"max_discount_pct": "100"}},
        {"alternative_type": "settlement_discount", "note": "x" * 201},
        {},
    ],
)
def test_invalid_approve_bodies_are_rejected(client: TestClient, payload: dict[str, Any]) -> None:
    proposal_id = _create(client)["proposal_id"]
    response = client.post(f"{BASE}/proposals/{proposal_id}/approve", json=payload)
    assert response.status_code == 422
    assert client.get(f"{BASE}/proposals/{proposal_id}").json()["status"] == "PENDING_MERCHANT"
