"""F1-20 integration test for persisted LLM fallback auditing."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.models import CustomerRow, InvoiceRow

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"


@pytest.fixture
def seeded_invoice(db_session: Session) -> None:
    db_session.add(
        CustomerRow(
            id="CUS-001",
            name="Acme Corp",
            email="billing@example.com",
        )
    )
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


@pytest.mark.usefixtures("seeded_invoice")
@respx.mock
def test_gemini_503_fallback_persists_warn_audit(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-test")
    monkeypatch.setenv("LLM_API_KEY", "fake-secret-not-for-logs")
    get_settings.cache_clear()

    route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(503))

    response = client.post(
        "/api/v1/invoices/INV-001/proposals",
        json={
            "customer_message": "Can I pay in three installments?",
        },
        headers={"Idempotency-Key": "f1-20-fallback-503"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["paypal_called"] is False
    assert body["blocked_reasons"][0]["code"] == "CLARIFICATION_REQUIRED"
    assert route.call_count == 2

    audit_response = client.get(
        "/api/v1/audit-events",
        params={"proposal_id": body["proposal_id"]},
    )

    assert audit_response.status_code == 200
    events = audit_response.json()["items"]

    assert [event["action"] for event in events] == [
        "LLM_FALLBACK_ACTIVATED",
        "PROPOSAL_BLOCKED",
    ]
    assert events[0]["severity"] == "WARN"
    assert events[0]["rule"]["code"] == "LLM_FALLBACK_ACTIVATED"
    assert events[0]["rule"]["attempted"] == "intent:PROVIDER_UNAVAILABLE"
    assert events[0]["source"] == "API"
    assert events[0]["actor"]["type"] == "SYSTEM"
    assert events[0]["paypal_called"] is False
    assert events[1]["state_from"] == "DRAFTED"
    assert events[1]["state_to"] == "BLOCKED"

    assert body["audit_event"]["action"] == "PROPOSAL_BLOCKED"

    audit_text = str(events)
    assert "fake-secret-not-for-logs" not in audit_text
    assert "Can I pay in three installments?" not in audit_text


@pytest.mark.usefixtures("seeded_invoice")
@respx.mock
def test_gemini_success_creates_approved_proposal(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """A valid LLM response passes finance, policy, and Text Guard."""
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-test")
    monkeypatch.setenv("LLM_API_KEY", "fake-test-key")
    get_settings.cache_clear()

    def gemini_response(text: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
        )

    route = respx.post(GEMINI_URL).mock(
        side_effect=[
            gemini_response('{"preferred_installments": 3}'),
            gemini_response("The approved payment alternatives are available."),
            gemini_response("Please review the proposed payment options."),
        ]
    )

    response = client.post(
        "/api/v1/invoices/INV-001/proposals",
        json={
            "customer_message": "Can I pay in three installments?",
        },
        headers={"Idempotency-Key": "f1-20-success"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "PENDING_MERCHANT"
    assert body["policy_check"]["status"] == "PASSED"
    assert body["text_number_check"]["status"] == "PASSED"
    assert len(body["alternatives"]) == 2
    assert body["paypal_called"] is False
    assert route.call_count == 3

    audit_response = client.get(
        "/api/v1/audit-events",
        params={"proposal_id": body["proposal_id"]},
    )
    assert audit_response.status_code == 200

    events = audit_response.json()["items"]
    assert [event["action"] for event in events] == ["PROPOSAL_DRAFTED"]
    assert body["audit_event"]["action"] == "PROPOSAL_DRAFTED"


@pytest.mark.usefixtures("seeded_invoice")
@respx.mock
def test_gemini_policy_violation_skips_text_generation(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """Policy violations stop before either LLM text-generation call."""
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-test")
    monkeypatch.setenv("LLM_API_KEY", "fake-test-key")
    get_settings.cache_clear()

    route = respx.post(GEMINI_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"requested_discount_pct": "40"}'}]}}
                ]
            },
        )
    )

    response = client.post(
        "/api/v1/invoices/INV-001/proposals",
        json={
            "customer_message": "Can I have a 40% discount?",
        },
        headers={"Idempotency-Key": "f1-20-policy-block"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "BLOCKED"
    assert body["paypal_called"] is False
    assert body["alternatives"] == []
    assert body["blocked_reasons"][0]["code"] == "MAX_DISCOUNT_PCT"
    assert body["explanation"] is None
    assert body["customer_message_draft"] is None

    # One intent-extraction call; no explanation or draft requests.
    assert route.call_count == 1


@pytest.mark.usefixtures("seeded_invoice")
@respx.mock
def test_gemini_invented_amount_is_blocked_by_text_guard(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """Reject an invented financial amount without activating fallback."""
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-test")
    monkeypatch.setenv("LLM_API_KEY", "fake-test-key")
    get_settings.cache_clear()

    def response(text: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
        )

    route = respx.post(GEMINI_URL).mock(
        side_effect=[
            response('{"preferred_installments": 3}'),
            response("The approved total is $99999.99."),
            response("Please review the payment options."),
        ]
    )

    result = client.post(
        "/api/v1/invoices/INV-001/proposals",
        json={"customer_message": "Can I pay in three installments?"},
        headers={"Idempotency-Key": "f1-20-invented-amount"},
    )

    assert result.status_code == 200
    body = result.json()

    assert body["status"] == "BLOCKED"
    assert body["policy_check"]["status"] == "PASSED"
    assert body["text_number_check"]["status"] == "FAILED"
    assert body["blocked_reasons"][0]["code"] == "TEXT_NUMBER_MISMATCH"
    assert body["paypal_called"] is False
    assert route.call_count == 3

    audit = client.get(
        "/api/v1/audit-events",
        params={"proposal_id": body["proposal_id"]},
    )

    assert audit.status_code == 200
    actions = [event["action"] for event in audit.json()["items"]]

    assert actions == ["PROPOSAL_BLOCKED"]
    assert "LLM_FALLBACK_ACTIVATED" not in actions
