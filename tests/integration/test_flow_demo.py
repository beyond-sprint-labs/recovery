"""Demo-flow integration skeleton (F1-08).

The active tests prove today that the seeded app boots and that the scenario catalog exposes the
blocking case. Every API step is marked ``xfail(strict=True)``: the PR that implements a step
must delete its marker, otherwise CI reports the unexpected pass as a failure.
"""

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.db import get_session_factory
from app.core.models import CustomerRow, InvoiceRow
from app.seed.loader import seed_database

API = "/api/v1"
SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "scenarios.json"
BLOCKED_SCENARIO_ID = "S03_exceeds_discount"
BLOCKED_MESSAGE = "Can I get 40% off if I pay this week?"
WITHIN_POLICY_MESSAGE = "I can pay part of it now and the rest in 3 installments."
EXPECTED_AUDIT_TRAIL = [
    "PROPOSAL_DRAFTED",
    "PROPOSAL_APPROVED",
    "CUSTOMER_LINK_ISSUED",
    "CUSTOMER_ACCEPTED",
    "EXECUTION_STARTED",
    "PAYPAL_DRAFT_CREATED",
    "PAYPAL_ORIGINAL_CANCELLED",
    "PAYPAL_INVOICE_SENT",
    "EXECUTION_COMPLETED",
]


class MissingDemoRoute(AssertionError):
    """Only an unimplemented route may be an expected failure."""


def _request(client: TestClient, method: str, path: str, **kwargs: Any) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    if response.status_code == 404:
        raise MissingDemoRoute(f"{method} {path}: HTTP 404; route not implemented")
    return response


def _pending(step: str, raises: type[BaseException] = MissingDemoRoute) -> pytest.MarkDecorator:
    return pytest.mark.xfail(
        strict=True,
        raises=raises,
        reason=f"Pending {step}; remove this marker when the step is implemented",
    )


def _scenario_ids() -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, str):
            if re.fullmatch(r"S[0-9]{2}(?:_[A-Za-z0-9_]+)?", node):
                found.add(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(SCENARIOS_PATH.read_text(encoding="utf-8")))
    return found


def _within_policy_scenario_id() -> str:
    matches = sorted(sid for sid in _scenario_ids() if sid == "S01" or sid.startswith("S01_"))
    if not matches:
        pytest.fail("Scenario catalog has no S01 entry")
    return matches[0]


def _create_proposal(
    client: TestClient, scenario_id: str, message: str, key: str | None = None
) -> Any:
    return _request(
        client,
        "POST",
        f"{API}/invoices/INV-001/proposals",
        headers={"Idempotency-Key": key or str(uuid4())},
        json={"customer_message": message, "scenario_id": scenario_id},
    )


def _token_from_link(link: str) -> str:
    return link.rstrip("/").rsplit("/", 1)[-1]


def _approved_proposal(client: TestClient) -> tuple[str, str]:
    created = _create_proposal(client, _within_policy_scenario_id(), WITHIN_POLICY_MESSAGE)
    assert created.status_code == 200
    proposal = created.json()
    assert proposal["status"] == "PENDING_MERCHANT"
    approved = _request(
        client,
        "POST",
        f"{API}/proposals/{proposal['proposal_id']}/approve",
        json={"alternative_type": "settlement_discount", "note": None},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "PENDING_CUSTOMER"
    return body["proposal_id"], _token_from_link(body["customer_link"])


@pytest.fixture
def seeded_client(client: TestClient) -> TestClient:
    with get_session_factory().begin() as session:
        seed_database(session)
    return client


# --- Active today ---------------------------------------------------------------------------


def test_seeded_app_boots_with_demo_data(seeded_client: TestClient) -> None:
    health = _request(seeded_client, "GET", "/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(CustomerRow)) == 3
        assert session.scalar(select(func.count()).select_from(InvoiceRow)) == 5
        invoice = session.get(InvoiceRow, "INV-001")
        assert invoice is not None
        assert (invoice.balance, invoice.status) == ("1000.00", "OVERDUE")


def test_audit_feed_is_empty_after_seeding(seeded_client: TestClient) -> None:
    response = _request(seeded_client, "GET", f"{API}/audit-events")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_scenario_catalog_exposes_the_demo_blocking_case() -> None:
    assert BLOCKED_SCENARIO_ID in _scenario_ids()


# --- Pending API steps ----------------------------------------------------------------------


# @_pending("F1-13 GET /invoices")
def test_invoices_list_exposes_seed_without_customer_data(seeded_client: TestClient) -> None:
    response = _request(seeded_client, "GET", f"{API}/invoices")
    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert "INV-001" in items
    assert items["INV-001"]["balance"] == "1000.00"
    assert items["INV-001"]["status"] == "OVERDUE"
    for item in items.values():
        assert "email" not in item
        assert "customer_id" not in item


# @_pending("F1-13 GET /policy")
def test_policy_endpoint_serves_server_side_limits(seeded_client: TestClient) -> None:
    response = _request(seeded_client, "GET", f"{API}/policy")
    assert response.status_code == 200
    body = response.json()
    assert (body["currency"], body["max_discount_pct"], body["max_installments"]) == (
        "USD",
        "15",
        6,
    )


# @_pending("F1-13/F1-15 blocked proposal")
def test_s03_discount_is_blocked_with_http_200_and_audit_event(seeded_client: TestClient) -> None:
    response = _create_proposal(seeded_client, BLOCKED_SCENARIO_ID, BLOCKED_MESSAGE)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["alternatives"] == []
    assert body["paypal_called"] is False
    reason = body["blocked_reasons"][0]
    assert (reason["code"], reason["limit"], reason["attempted"], reason["unit"]) == (
        "MAX_DISCOUNT_PCT",
        "15",
        "40",
        "pct",
    )
    event = body["audit_event"]
    assert (event["action"], event["severity"], event["state_from"], event["state_to"]) == (
        "PROPOSAL_BLOCKED",
        "CRITICAL",
        "DRAFTED",
        "BLOCKED",
    )
    assert event["paypal_called"] is False
    feed = _request(
        seeded_client, "GET", f"{API}/audit-events", params={"proposal_id": body["proposal_id"]}
    )
    assert feed.status_code == 200
    assert [item["event_id"] for item in feed.json()["items"]] == [event["event_id"]]


# @_pending("F1-15 blocked proposals are terminal")
def test_blocked_proposal_cannot_be_approved(seeded_client: TestClient) -> None:
    blocked = _create_proposal(seeded_client, BLOCKED_SCENARIO_ID, BLOCKED_MESSAGE).json()
    response = _request(
        seeded_client,
        "POST",
        f"{API}/proposals/{blocked['proposal_id']}/approve",
        json={"alternative_type": "settlement_discount", "note": None},
    )
    assert response.status_code == 409


# @_pending("F1-13 strict CreateProposalIn")
def test_policy_in_request_body_is_rejected(seeded_client: TestClient) -> None:
    response = _request(
        seeded_client,
        "POST",
        f"{API}/invoices/INV-001/proposals",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "customer_message": BLOCKED_MESSAGE,
            "scenario_id": BLOCKED_SCENARIO_ID,
            "policy": {"max_discount_pct": "100"},
        },
    )
    assert response.status_code == 422


# @_pending("F1-13 Idempotency-Key is mandatory")
def test_missing_idempotency_key_is_rejected(seeded_client: TestClient) -> None:
    response = _request(
        seeded_client,
        "POST",
        f"{API}/invoices/INV-001/proposals",
        json={"customer_message": BLOCKED_MESSAGE, "scenario_id": BLOCKED_SCENARIO_ID},
    )
    assert response.status_code == 422


# @_pending("F1-13 idempotent proposal creation")
def test_same_idempotency_key_returns_same_proposal(seeded_client: TestClient) -> None:
    key = str(uuid4())
    first = _create_proposal(seeded_client, BLOCKED_SCENARIO_ID, BLOCKED_MESSAGE, key)
    second = _create_proposal(seeded_client, BLOCKED_SCENARIO_ID, BLOCKED_MESSAGE, key)
    assert first.status_code == second.status_code == 200
    proposal_id = first.json()["proposal_id"]
    assert second.json()["proposal_id"] == proposal_id
    feed = _request(
        seeded_client, "GET", f"{API}/audit-events", params={"proposal_id": proposal_id}
    )
    assert [item["action"] for item in feed.json()["items"]] == ["PROPOSAL_BLOCKED"]


# @_pending("F1-13 approve and customer view")
def test_customer_view_exposes_one_alternative_and_keeps_token(seeded_client: TestClient) -> None:
    _, token = _approved_proposal(seeded_client)
    path = f"{API}/customer/proposals/{token}"
    view = _request(seeded_client, "GET", path)
    assert view.status_code == 200
    body = view.json()
    assert {"alternatives", "policy_check", "blocked_reasons", "attempted"}.isdisjoint(body)
    assert {"present_value", "merchant_difference_vs_balance"}.isdisjoint(body["alternative"])
    assert _request(seeded_client, "GET", path).status_code == 200


@_pending("F1-12 walking skeleton: respond and mock execution", raises=AssertionError)
def test_double_accept_executes_once(seeded_client: TestClient) -> None:
    _, token = _approved_proposal(seeded_client)
    path = f"{API}/customer/proposals/{token}/respond"
    first = _request(seeded_client, "POST", path, json={"decision": "ACCEPT"})
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "EXECUTED"
    assert body["paypal"]["new_invoice_id"].startswith("MOCK-INV-")
    second = _request(seeded_client, "POST", path, json={"decision": "ACCEPT"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "TOKEN_ALREADY_USED"


@_pending("F1-12 walking skeleton: complete audit trail", raises=AssertionError)
def test_executed_flow_leaves_the_full_audit_trail(seeded_client: TestClient) -> None:
    proposal_id, token = _approved_proposal(seeded_client)
    responded = _request(
        seeded_client,
        "POST",
        f"{API}/customer/proposals/{token}/respond",
        json={"decision": "ACCEPT"},
    )
    assert responded.status_code == 200
    feed = _request(
        seeded_client,
        "GET",
        f"{API}/audit-events",
        params={"proposal_id": proposal_id, "limit": 100},
    )
    assert feed.status_code == 200
    items = feed.json()["items"]
    seqs = [item["seq"] for item in items]
    assert seqs == sorted(set(seqs))
    actions = iter(item["action"] for item in items)
    assert all(expected in actions for expected in EXPECTED_AUDIT_TRAIL)
