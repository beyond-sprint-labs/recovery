"""HTTP-level tests for the Slice 1 endpoints (F1-13)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.models import CustomerRow, InvoiceRow

BASE = "/api/v1"


@pytest.fixture
def seeded(db_session: Session) -> None:
    db_session.add(CustomerRow(id="CUS-001", name="Acme Corp", email="billing@example.com"))
    db_session.flush()
    db_session.add_all(
        [
            InvoiceRow(
                id="INV-001",
                customer_id="CUS-001",
                customer_name="Acme Corp",
                currency="USD",
                balance="1000.00",
                due_date="2026-10-15",
                status="OVERDUE",
                paypal_invoice_id=None,
            ),
            InvoiceRow(
                id="INV-002",
                customer_id="CUS-001",
                customer_name="Acme Corp",
                currency="USD",
                balance="0.00",
                due_date="2026-09-01",
                status="PAID",
                paypal_invoice_id=None,
            ),
        ]
    )
    db_session.commit()


def _post(
    client: TestClient,
    message: str,
    scenario: str | None = None,
    *,
    invoice_id: str = "INV-001",
    key: str | None = None,
) -> Any:
    payload: dict[str, Any] = {"customer_message": message}
    if scenario is not None:
        payload["scenario_id"] = scenario
    return client.post(
        f"{BASE}/invoices/{invoice_id}/proposals",
        json=payload,
        headers={"Idempotency-Key": key or str(uuid.uuid4())},
    )


@pytest.mark.usefixtures("seeded")
def test_s01_returns_the_golden_figures(client: TestClient) -> None:
    response = _post(client, "I can pay 300 now, in 3 parts", "S01_partial_payment_now")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "PENDING_MERCHANT"
    assert body["paypal_called"] is False
    assert body["blocked_reasons"] == []
    settlement, plan = body["alternatives"]
    assert settlement["amount_due_now"] == "900.00"
    assert settlement["merchant_difference_vs_balance"] == "-100.00"
    assert plan["amount_due_now"] == "300.00"
    assert plan["installment_amount"] == "240.37"
    assert plan["total_paid"] == "1021.10"
    assert plan["present_value"] == "1006.91"
    assert plan["merchant_difference_vs_balance"] == "6.91"
    assert [row["amount"] for row in plan["schedule"]] == ["300.00", "240.37", "240.37", "240.36"]
    assert body["policy_check"]["status"] == "PASSED"
    assert body["text_number_check"]["status"] == "PASSED"
    assert "$900.00" in body["explanation"]
    event = body["audit_event"]
    assert event["action"] == "PROPOSAL_DRAFTED"
    assert (event["state_from"], event["state_to"]) == ("DRAFTED", "PENDING_MERCHANT")
    assert event["severity"] == "INFO"


@pytest.mark.usefixtures("seeded")
def test_s03_exceeding_the_discount_limit_is_blocked_with_http_200(client: TestClient) -> None:
    response = _post(client, "Can I get 40% off?", "S03_exceeds_discount")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "BLOCKED"
    assert body["alternatives"] == []
    assert body["blocked_reasons"] == [
        {
            "code": "MAX_DISCOUNT_PCT",
            "message": "Requested discount 40% exceeds merchant limit 15%",
            "limit": "15",
            "attempted": "40",
            "unit": "pct",
        }
    ]
    assert body["attempted"][0]["computed"] == {
        "amount_due_now": "600.00",
        "merchant_difference_vs_balance": "-400.00",
    }
    assert body["policy_check"]["status"] == "BLOCKED"
    assert body["text_number_check"]["status"] == "SKIPPED"
    assert body["paypal_called"] is False
    event = body["audit_event"]
    assert event["action"] == "PROPOSAL_BLOCKED"
    assert event["severity"] == "CRITICAL"
    assert event["actor"]["id"] == "policy_engine"
    assert event["proposed_by"]["id"] == "agent_v1"
    assert event["rule"]["code"] == "MAX_DISCOUNT_PCT"
    assert event["summary"] == (
        "AI-proposed 40% settlement discount exceeds merchant limit of 15%; PayPal not called"
    )
    assert event["state_from"] == "DRAFTED"


@pytest.mark.usefixtures("seeded")
def test_s11_tampered_text_is_blocked_by_the_text_guard(client: TestClient) -> None:
    body = _post(client, "3 installments please", "S11_text_mismatch").json()
    assert body["status"] == "BLOCKED"
    assert body["blocked_reasons"][0]["code"] == "TEXT_NUMBER_MISMATCH"
    assert body["text_number_check"]["status"] == "FAILED"
    assert "850.00" in body["text_number_check"]["unmatched"]
    assert body["policy_check"]["status"] == "PASSED"
    assert body["explanation"] is None
    assert body["customer_message_draft"] is None
    assert body["audit_event"]["severity"] == "CRITICAL"


@pytest.mark.usefixtures("seeded")
def test_s10_invalid_discount_is_blocked_as_invalid_agent_output(client: TestClient) -> None:
    body = _post(client, "Give me 150% off", "S10_invalid_discount_150").json()
    assert body["status"] == "BLOCKED"
    assert body["blocked_reasons"][0]["code"] == "INVALID_AGENT_OUTPUT"
    assert body["audit_event"]["severity"] == "CRITICAL"


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    "scenario",
    [None, "S05_ambiguous_slow_business", "S08_injection_ignore_instructions"],
)
def test_messages_without_a_concrete_request_need_clarification(
    client: TestClient, scenario: str | None
) -> None:
    response = _post(client, "Business has been slow lately", scenario)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["blocked_reasons"][0]["code"] == "CLARIFICATION_REQUIRED"
    assert body["audit_event"]["severity"] == "WARN"
    assert body["paypal_called"] is False


@pytest.mark.usefixtures("seeded")
def test_hidden_characters_are_audited_before_the_decision(client: TestClient) -> None:
    body = _post(client, "Can I get 4\u200b0% off?", "S12_hidden_characters").json()
    assert body["status"] == "BLOCKED"
    assert body["blocked_reasons"][0]["code"] == "MAX_DISCOUNT_PCT"

    events = client.get(f"{BASE}/audit-events", params={"proposal_id": body["proposal_id"]}).json()[
        "items"
    ]
    assert [event["action"] for event in events] == ["INPUT_SANITIZED", "PROPOSAL_BLOCKED"]
    assert events[0]["severity"] == "WARN"
    assert events[0]["rule"]["code"] == "CONTROL_CHARS_STRIPPED"


@pytest.mark.usefixtures("seeded")
def test_same_idempotency_key_replays_the_same_proposal(client: TestClient) -> None:
    key = str(uuid.uuid4())
    first = _post(client, "I can pay 300 now", "S01_partial_payment_now", key=key)
    second = _post(client, "I can pay 300 now", "S01_partial_payment_now", key=key)
    assert second.status_code == 200
    assert second.json() == first.json()

    events = client.get(
        f"{BASE}/audit-events", params={"proposal_id": first.json()["proposal_id"]}
    ).json()["items"]
    assert len(events) == 1  # the replay did not re-run the pipeline


@pytest.mark.usefixtures("seeded")
def test_reusing_a_key_for_another_request_conflicts(client: TestClient) -> None:
    key = str(uuid.uuid4())
    assert _post(client, "I can pay 300 now", "S01_partial_payment_now", key=key).status_code == 200
    response = _post(client, "Can I get 40% off?", "S03_exceeds_discount", key=key)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.usefixtures("seeded")
def test_missing_idempotency_header_is_a_validation_error(client: TestClient) -> None:
    response = client.post(f"{BASE}/invoices/INV-001/proposals", json={"customer_message": "hi"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.usefixtures("seeded")
def test_policy_in_the_request_body_is_rejected(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/invoices/INV-001/proposals",
        json={"customer_message": "hi", "policy": {"max_discount_pct": "100"}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422


@pytest.mark.usefixtures("seeded")
def test_message_that_is_empty_after_sanitization_is_rejected(client: TestClient) -> None:
    response = _post(client, "\u200b\u200b\u200b")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_MESSAGE"


@pytest.mark.usefixtures("seeded")
def test_unknown_and_non_overdue_invoices_are_rejected(client: TestClient) -> None:
    missing = _post(client, "hello", invoice_id="INV-404")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "INVOICE_NOT_FOUND"

    paid = _post(client, "hello", invoice_id="INV-002")
    assert paid.status_code == 409
    assert paid.json()["error"]["code"] == "INVOICE_NOT_OVERDUE"


@pytest.mark.usefixtures("seeded")
def test_get_proposal_matches_the_creation_response(client: TestClient) -> None:
    created = _post(client, "Can I get 40% off?", "S03_exceeds_discount").json()
    fetched = client.get(f"{BASE}/proposals/{created['proposal_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


@pytest.mark.usefixtures("seeded")
def test_get_unknown_proposal_is_404(client: TestClient) -> None:
    response = client.get(f"{BASE}/proposals/prop_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"


@pytest.mark.usefixtures("seeded")
def test_invoice_endpoints_expose_only_the_public_contract(client: TestClient) -> None:
    listing = client.get(f"{BASE}/invoices")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == ["INV-001", "INV-002"]

    single = client.get(f"{BASE}/invoices/INV-001").json()
    assert set(single) == {
        "id",
        "customer_name",
        "currency",
        "balance",
        "due_date",
        "status",
        "paypal_invoice_id",
    }
    assert single["balance"] == "1000.00"
    assert client.get(f"{BASE}/invoices/INV-404").status_code == 404


def test_policy_endpoint_returns_the_server_policy(client: TestClient) -> None:
    assert client.get(f"{BASE}/policy").json() == {
        "currency": "USD",
        "max_discount_pct": "15",
        "min_down_payment_pct": "20",
        "max_installments": 6,
        "max_financing_rate_pct": "2.0",
        "merchant_discount_rate_pct": "1.0",
    }


@pytest.mark.usefixtures("seeded")
def test_server_defaults_never_auto_block_a_stricter_policy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POLICY_MAX_DISCOUNT_PCT", "5")
    monkeypatch.setenv("POLICY_MIN_DOWN_PAYMENT_PCT", "40")
    get_settings.cache_clear()

    body = _post(client, "I can pay 300 now, in 3 parts", "S01_partial_payment_now").json()
    assert body["status"] == "PENDING_MERCHANT"
    settlement, plan = body["alternatives"]
    assert settlement["terms"] == {"discount_pct": "5"}
    assert settlement["amount_due_now"] == "950.00"
    assert plan["terms"]["down_payment_pct"] == "40"
    assert plan["amount_due_now"] == "400.00"
