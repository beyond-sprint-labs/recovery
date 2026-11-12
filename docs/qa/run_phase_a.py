#!/usr/bin/env python3
"""F1-23 Phase A functional QA harness.

Runs S01-S12 through the public HTTP contract against an isolated SQLite
database, the demo seed, the mock PayPal gateway and the scripted agent.
It writes machine-readable evidence under ``docs/evidence/F1-23/`` and a
generated matrix under ``docs/qa/``.

Run from the repository root:

    .venv\\Scripts\\python.exe docs\\qa\\run_phase_a.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = ROOT / "docs" / "evidence" / "F1-23"
QA_ROOT = ROOT / "docs" / "qa"
SCENARIOS_PATH = ROOT / "tests" / "scenarios" / "scenarios.json"
API = "/api/v1"

# Customer links and API paths carry a single-use token. Evidence is committed,
# so the token is redacted; the harness regenerates it on every run.
_TOKEN_RE = re.compile(r"(/customer/(?:proposals/)?)([A-Za-z0-9_-]{20,})")

_SEED_INVOICES = {
    "INV-001": ("1000.00", "OVERDUE"),
    "INV-002": ("250.50", "OVERDUE"),
    "INV-003": ("1500.00", "OVERDUE"),
    "INV-004": ("0.00", "PAID"),
    "INV-005": ("400.00", "CANCELLED"),
}

_EXPECTED_POLICY = {
    "currency": "USD",
    "max_discount_pct": "15",
    "min_down_payment_pct": "20",
    "max_installments": 6,
    "max_financing_rate_pct": "2.0",
    "merchant_discount_rate_pct": "1.0",
}

_EXPECTED_AUDIT_TRAIL = [
    "PROPOSAL_DRAFTED",
    "PROPOSAL_APPROVED",
    "CUSTOMER_LINK_ISSUED",
    "CUSTOMER_ACCEPTED",
    "EXECUTION_STARTED",
    "PAYPAL_DRAFT_CREATED",
    "PAYPAL_ORIGINAL_CANCELLED",
    "PAYPAL_INVOICE_SENT",
    "EXECUTION_COMPLETED",
    "PAYMENT_CONFIRMED",
]

_BLOCKED_ITEMS = [
    {
        "id": "BLK-01",
        "scope": "PayPal Sandbox real",
        "dependency": "PAYPAL_MODE=real with sandbox client id/secret, registered webhook id, "
        "public HTTPS URL and sandbox buyer",
        "affected": "Real payment, real webhook signature verification, real invoice lifecycle",
        "status": "BLOCKED",
    },
    {
        "id": "BLK-02",
        "scope": "LLM real (F1-20)",
        "dependency": "Merge feat/f1-20-real-llm-agent and configure the provider/API key",
        "affected": "S07 tone quality, S08/S09 real-LLM injection resistance, real text generation",
        "status": "BLOCKED",
    },
    {
        "id": "BLK-03",
        "scope": "UI",
        "dependency": "Merge feat/ui-skeleton-mocks and deploy the frontend",
        "affected": "Browser E2E, customer portal UX and visual evidence",
        "status": "BLOCKED",
    },
    {
        "id": "BLK-04",
        "scope": "Deployed environment",
        "dependency": "Public environment URL and deployment credentials",
        "affected": "Deployed E2E and environment-specific checks",
        "status": "BLOCKED",
    },
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def redact(value: Any) -> Any:
    """Remove single-use customer tokens from committed evidence."""
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _TOKEN_RE.sub(r"\1<redacted>", value)
    return value


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(redact(data), indent=2, ensure_ascii=False, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")


def check(
    name: str,
    passed: bool,
    expected: Any,
    actual: Any,
    *,
    critical: bool = True,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "check": name,
        "passed": bool(passed),
        "critical": critical,
        "expected": expected,
        "actual": actual,
        "note": note,
    }


def configure_environment(db_path: Path) -> None:
    os.environ.update(
        {
            "APP_ENV": "local",
            "DEMO_MODE": "true",
            "PAYPAL_MODE": "mock",
            "AGENT_MODE": "scripted",
            "ALLOW_SCENARIO_ID": "true",
            "ALLOW_SANDBOX_PAYMENT_SHORTCUT": "false",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "PUBLIC_BASE_URL": "http://localhost:8000",
            "CORS_ORIGINS": "http://localhost:5173",
            "CUSTOMER_TOKEN_TTL_MIN": "1440",
            "POLICY_MAX_DISCOUNT_PCT": "15",
            "POLICY_MIN_DOWN_PAYMENT_PCT": "20",
            "POLICY_MAX_INSTALLMENTS": "6",
            "POLICY_MAX_FINANCING_RATE_PCT": "2.0",
            "MERCHANT_DISCOUNT_RATE_PCT": "1.0",
        }
    )


def clear_caches() -> None:
    from app.core.config import get_settings
    from app.core.db import get_engine, get_session_factory
    from app.core.deps import get_paypal_gateway

    get_paypal_gateway.cache_clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()


def new_client(db_path: Path) -> Any:
    from fastapi.testclient import TestClient

    configure_environment(db_path)
    clear_caches()
    from app.main import create_app

    return TestClient(create_app())


def call(client: Any, method: str, path: str, **kwargs: Any) -> tuple[Any, Any]:
    response = client.request(method, API + path, **kwargs)
    try:
        body = response.json()
    except ValueError:
        body = {"_raw": response.text}
    return response, body


def call_root(client: Any, method: str, path: str, **kwargs: Any) -> tuple[Any, Any]:
    response = client.request(method, path, **kwargs)
    try:
        body = response.json()
    except ValueError:
        body = {"_raw": response.text}
    return response, body


def expected_api(scenario: dict[str, Any]) -> dict[str, str | None]:
    """Map the business vocabulary in scenarios.json to the API contract."""
    outcome = scenario["expected_outcome"]
    if outcome == "PENDING_MERCHANT":
        return {"status": "PENDING_MERCHANT", "code": None}
    if outcome == "BLOCKED":
        return {"status": "BLOCKED", "code": scenario.get("expected_rule_code")}
    if outcome == "CLARIFICATION":
        return {"status": "BLOCKED", "code": "CLARIFICATION_REQUIRED"}
    if outcome == "INVALID_AGENT_OUTPUT":
        return {"status": "BLOCKED", "code": "INVALID_AGENT_OUTPUT"}
    return {"status": outcome, "code": None}


def get_events(client: Any, proposal_id: str) -> tuple[Any, Any]:
    return call(
        client,
        "GET",
        "/audit-events",
        params={"proposal_id": proposal_id, "limit": 100},
    )


def alternative_arithmetic(alternative: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    amount_due_now = Decimal(alternative["amount_due_now"])
    total_paid = Decimal(alternative["total_paid"])
    schedule = alternative.get("schedule") or []
    schedule_total = sum((Decimal(row["amount"]) for row in schedule), Decimal("0"))
    checks.append(
        check(
            "schedule total equals total_paid",
            schedule_total == total_paid,
            str(total_paid),
            str(schedule_total),
        )
    )
    if schedule:
        checks.append(
            check(
                "first schedule row equals amount_due_now",
                Decimal(schedule[0]["amount"]) == amount_due_now,
                str(amount_due_now),
                schedule[0]["amount"],
            )
        )
    if alternative["type"] == "down_payment_installments":
        terms = alternative["terms"]
        checks.append(
            check(
                "installment schedule length is installments + 1",
                len(schedule) == int(terms["installments"]) + 1,
                int(terms["installments"]) + 1,
                len(schedule),
            )
        )
    if alternative["type"] == "settlement_discount":
        checks.append(
            check(
                "settlement total equals amount_due_now",
                total_paid == amount_due_now,
                str(amount_due_now),
                str(total_paid),
            )
        )
    return checks


def validate_blocked(
    client: Any,
    scenario: dict[str, Any],
    body: dict[str, Any],
    directory: Path,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = [
        check(
            "no alternatives offered", body.get("alternatives") == [], [], body.get("alternatives")
        ),
        check(
            "PayPal not called",
            body.get("paypal_called") is False,
            False,
            body.get("paypal_called"),
        ),
        check(
            "blocked reasons present",
            bool(body.get("blocked_reasons")),
            True,
            body.get("blocked_reasons"),
        ),
    ]

    scenario_id = scenario["id"].split("_", 1)[0]
    if scenario["expected_outcome"] == "BLOCKED" and scenario_id != "S11":
        checks.append(
            check(
                "policy_check is BLOCKED",
                body["policy_check"]["status"] == "BLOCKED",
                "BLOCKED",
                body["policy_check"]["status"],
            )
        )
        checks.append(
            check(
                "text_number_check is SKIPPED",
                body["text_number_check"]["status"] == "SKIPPED",
                "SKIPPED",
                body["text_number_check"]["status"],
            )
        )

    if scenario_id == "S11":
        checks.extend(
            [
                check(
                    "policy_check is PASSED",
                    body["policy_check"]["status"] == "PASSED",
                    "PASSED",
                    body["policy_check"]["status"],
                ),
                check(
                    "text_number_check is FAILED",
                    body["text_number_check"]["status"] == "FAILED",
                    "FAILED",
                    body["text_number_check"]["status"],
                ),
                check(
                    "unmatched contains 850.00",
                    "850.00" in body["text_number_check"]["unmatched"],
                    True,
                    body["text_number_check"]["unmatched"],
                ),
                check(
                    "explanation is None",
                    body.get("explanation") is None,
                    None,
                    body.get("explanation"),
                ),
                check(
                    "customer draft is None",
                    body.get("customer_message_draft") is None,
                    None,
                    body.get("customer_message_draft"),
                ),
            ]
        )

    if scenario_id == "S12":
        events_response, events = get_events(client, body["proposal_id"])
        dump(
            directory / "08-audit-events.json",
            {"status_code": events_response.status_code, "body": events, "ts": utc_now()},
        )
        items = events.get("items", [])
        actions = [event["action"] for event in items]
        sanitized = [event for event in items if event["action"] == "INPUT_SANITIZED"]
        checks.extend(
            [
                check(
                    "INPUT_SANITIZED audit event",
                    "INPUT_SANITIZED" in actions,
                    "INPUT_SANITIZED",
                    actions,
                ),
                check(
                    "CONTROL_CHARS_STRIPPED rule",
                    bool(sanitized) and sanitized[0]["rule"]["code"] == "CONTROL_CHARS_STRIPPED",
                    "CONTROL_CHARS_STRIPPED",
                    sanitized[0]["rule"]["code"] if sanitized else None,
                ),
                check(
                    "PROPOSAL_BLOCKED audit event",
                    "PROPOSAL_BLOCKED" in actions,
                    "PROPOSAL_BLOCKED",
                    actions,
                ),
            ]
        )

    if scenario_id == "S03":
        attempted = body.get("attempted") or []
        checks.append(
            check("attempted alternative captured", len(attempted) >= 1, ">=1", len(attempted))
        )

    return checks


def validate_pending(
    client: Any,
    scenario: dict[str, Any],
    body: dict[str, Any],
    directory: Path,
) -> list[dict[str, Any]]:
    scenario_id = scenario["id"].split("_", 1)[0]
    checks: list[dict[str, Any]] = [
        check(
            "policy_check is PASSED",
            body["policy_check"]["status"] == "PASSED",
            "PASSED",
            body["policy_check"]["status"],
        ),
        check(
            "text_number_check is PASSED",
            body["text_number_check"]["status"] == "PASSED",
            "PASSED",
            body["text_number_check"]["status"],
        ),
        check(
            "PayPal not called during drafting",
            body["paypal_called"] is False,
            False,
            body["paypal_called"],
        ),
        check(
            "two alternatives offered", len(body["alternatives"]) == 2, 2, len(body["alternatives"])
        ),
    ]

    alternatives = {alternative["type"]: alternative for alternative in body["alternatives"]}
    for alternative in body["alternatives"]:
        checks.extend(alternative_arithmetic(alternative))

    if scenario_id in {"S01", "S02"}:
        chosen_type = "down_payment_installments"
    elif scenario_id == "S04":
        chosen_type = "settlement_discount"
    else:
        chosen_type = body["alternatives"][0]["type"]

    chosen = alternatives.get(chosen_type)
    checks.append(
        check(
            "chosen alternative is offered", chosen is not None, chosen_type, sorted(alternatives)
        )
    )
    if chosen is None:
        return checks

    if scenario_id == "S01":
        settlement = alternatives["settlement_discount"]
        plan = alternatives["down_payment_installments"]
        checks.extend(
            [
                check(
                    "S01 settlement amount_due_now",
                    settlement["amount_due_now"] == "900.00",
                    "900.00",
                    settlement["amount_due_now"],
                ),
                check(
                    "S01 settlement merchant difference",
                    settlement["merchant_difference_vs_balance"] == "-100.00",
                    "-100.00",
                    settlement["merchant_difference_vs_balance"],
                ),
                check(
                    "S01 plan amount_due_now",
                    plan["amount_due_now"] == "300.00",
                    "300.00",
                    plan["amount_due_now"],
                ),
                check(
                    "S01 plan installment_amount",
                    plan["installment_amount"] == "240.37",
                    "240.37",
                    plan["installment_amount"],
                ),
                check(
                    "S01 plan total_paid",
                    plan["total_paid"] == "1021.10",
                    "1021.10",
                    plan["total_paid"],
                ),
                check(
                    "S01 plan present_value",
                    plan["present_value"] == "1006.91",
                    "1006.91",
                    plan["present_value"],
                ),
                check(
                    "S01 plan merchant difference",
                    plan["merchant_difference_vs_balance"] == "6.91",
                    "6.91",
                    plan["merchant_difference_vs_balance"],
                ),
                check(
                    "S01 schedule amounts",
                    [row["amount"] for row in plan["schedule"]]
                    == ["300.00", "240.37", "240.37", "240.36"],
                    ["300.00", "240.37", "240.37", "240.36"],
                    [row["amount"] for row in plan["schedule"]],
                ),
            ]
        )

    if scenario_id == "S02":
        plan = alternatives["down_payment_installments"]
        checks.extend(
            [
                check(
                    "S02 installment count",
                    plan["terms"]["installments"] == 3,
                    3,
                    plan["terms"]["installments"],
                ),
                check("S02 schedule length", len(plan["schedule"]) == 4, 4, len(plan["schedule"])),
            ]
        )

    if scenario_id == "S04":
        settlement = alternatives["settlement_discount"]
        checks.extend(
            [
                check(
                    "S04 settlement amount_due_now",
                    settlement["amount_due_now"] == "900.00",
                    "900.00",
                    settlement["amount_due_now"],
                ),
                check(
                    "S04 settlement discount_pct",
                    settlement["terms"]["discount_pct"] == "10",
                    "10",
                    settlement["terms"]["discount_pct"],
                ),
                check(
                    "S04 settlement merchant difference",
                    settlement["merchant_difference_vs_balance"] == "-100.00",
                    "-100.00",
                    settlement["merchant_difference_vs_balance"],
                ),
            ]
        )

    approve_response, approval = call(
        client,
        "POST",
        f"/proposals/{body['proposal_id']}/approve",
        json={"alternative_type": chosen_type, "note": "F1-23 Phase A QA"},
    )
    dump(
        directory / "03-approval.json",
        {
            "request": {"alternative_type": chosen_type, "note": "F1-23 Phase A QA"},
            "status_code": approve_response.status_code,
            "body": approval,
            "ts": utc_now(),
        },
    )
    checks.extend(
        [
            check(
                "approve HTTP 200",
                approve_response.status_code == 200,
                200,
                approve_response.status_code,
            ),
            check(
                "approve status PENDING_CUSTOMER",
                approval.get("status") == "PENDING_CUSTOMER",
                "PENDING_CUSTOMER",
                approval.get("status"),
            ),
            check(
                "approved alternative",
                approval.get("approved_alternative") == chosen_type,
                chosen_type,
                approval.get("approved_alternative"),
            ),
        ]
    )

    link = approval.get("customer_link", "")
    token = link.rstrip("/").rsplit("/", 1)[-1]
    checks.append(check("customer link issued", bool(token) and token != link, True, bool(token)))

    view_response, view = call(client, "GET", f"/customer/proposals/{token}")
    dump(
        directory / "04-customer-view.json",
        {
            "request": {"method": "GET", "path": f"{API}/customer/proposals/<redacted>"},
            "status_code": view_response.status_code,
            "body": view,
            "ts": utc_now(),
        },
    )
    expected_view_keys = {
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
    expected_alternative_keys = {
        "type",
        "terms",
        "amount_due_now",
        "installment_amount",
        "total_paid",
        "schedule",
    }
    view_raw = json.dumps(view, ensure_ascii=False)
    checks.extend(
        [
            check(
                "customer view HTTP 200",
                view_response.status_code == 200,
                200,
                view_response.status_code,
            ),
            check(
                "customer view status PENDING_CUSTOMER",
                view.get("status") == "PENDING_CUSTOMER",
                "PENDING_CUSTOMER",
                view.get("status"),
            ),
            check(
                "customer view original balance",
                view.get("original_balance") == "1000.00",
                "1000.00",
                view.get("original_balance"),
            ),
            check(
                "customer view keys",
                set(view) == expected_view_keys,
                sorted(expected_view_keys),
                sorted(view),
            ),
            check(
                "customer alternative keys",
                set(view["alternative"]) == expected_alternative_keys,
                sorted(expected_alternative_keys),
                sorted(view["alternative"]),
            ),
            check(
                "customer view alternative type",
                view["alternative"]["type"] == chosen_type,
                chosen_type,
                view["alternative"]["type"],
            ),
            check(
                "customer view amount matches proposal",
                view["alternative"]["amount_due_now"] == chosen["amount_due_now"],
                chosen["amount_due_now"],
                view["alternative"]["amount_due_now"],
            ),
            check(
                "customer view total matches proposal",
                view["alternative"]["total_paid"] == chosen["total_paid"],
                chosen["total_paid"],
                view["alternative"]["total_paid"],
            ),
        ]
    )
    for forbidden in (
        "present_value",
        "merchant_difference_vs_balance",
        "policy_check",
        "blocked_reasons",
    ):
        checks.append(
            check(
                f"customer view hides {forbidden}",
                forbidden not in view_raw,
                False,
                forbidden in view_raw,
            )
        )

    respond_response, responded = call(
        client,
        "POST",
        f"/customer/proposals/{token}/respond",
        json={"decision": "ACCEPT"},
    )
    dump(
        directory / "05-customer-response.json",
        {
            "request": {"decision": "ACCEPT"},
            "status_code": respond_response.status_code,
            "body": responded,
            "ts": utc_now(),
        },
    )
    paypal = responded.get("paypal") or {}
    new_invoice_id = paypal.get("new_invoice_id")
    checks.extend(
        [
            check(
                "respond HTTP 200",
                respond_response.status_code == 200,
                200,
                respond_response.status_code,
            ),
            check(
                "respond status EXECUTED",
                responded.get("status") == "EXECUTED",
                "EXECUTED",
                responded.get("status"),
            ),
            check(
                "mock PayPal invoice created",
                bool(new_invoice_id) and str(new_invoice_id).startswith("MOCK-INV-"),
                "MOCK-INV-*",
                new_invoice_id,
            ),
            check(
                "execution steps complete",
                {"preflight_ok", "draft_created", "original_cancelled", "draft_sent"}.issubset(
                    set(paypal.get("steps", []))
                ),
                ["preflight_ok", "draft_created", "original_cancelled", "draft_sent"],
                paypal.get("steps"),
            ),
        ]
    )

    webhook_body = {
        "id": f"WH-{uuid.uuid4().hex}",
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"invoice": {"id": new_invoice_id}},
    }
    webhook_response, webhook = call(client, "POST", "/webhooks/paypal", json=webhook_body)
    dump(
        directory / "06-webhook.json",
        {
            "request": webhook_body,
            "status_code": webhook_response.status_code,
            "body": webhook,
            "ts": utc_now(),
        },
    )
    checks.extend(
        [
            check(
                "webhook HTTP 200",
                webhook_response.status_code == 200,
                200,
                webhook_response.status_code,
            ),
            check(
                "webhook received", webhook.get("received") is True, True, webhook.get("received")
            ),
        ]
    )

    final_response, final = call(client, "GET", f"/proposals/{body['proposal_id']}")
    dump(
        directory / "07-final-proposal.json",
        {"status_code": final_response.status_code, "body": final, "ts": utc_now()},
    )
    checks.extend(
        [
            check(
                "final proposal HTTP 200",
                final_response.status_code == 200,
                200,
                final_response.status_code,
            ),
            check("final status PAID", final.get("status") == "PAID", "PAID", final.get("status")),
            check(
                "final PayPal invoice id",
                (final.get("paypal") or {}).get("new_invoice_id") == new_invoice_id,
                new_invoice_id,
                (final.get("paypal") or {}).get("new_invoice_id"),
            ),
        ]
    )

    events_response, events = get_events(client, body["proposal_id"])
    dump(
        directory / "08-audit-events.json",
        {"status_code": events_response.status_code, "body": events, "ts": utc_now()},
    )
    actions = [event["action"] for event in events.get("items", [])]
    checks.append(
        check(
            "full audit trail",
            all(action in actions for action in _EXPECTED_AUDIT_TRAIL),
            _EXPECTED_AUDIT_TRAIL,
            actions,
        )
    )

    return checks


def execute_scenario(client: Any, scenario: dict[str, Any], directory: Path) -> dict[str, Any]:
    scenario_id = scenario["id"].split("_", 1)[0]
    checks: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    idempotency_key = f"qa-f1-23-{scenario_id.lower()}-{uuid.uuid4().hex}"
    payload = {
        "customer_message": scenario["customer_message"],
        "scenario_id": scenario["id"],
    }

    dump(
        directory / "01-request.json",
        {
            "method": "POST",
            "path": f"{API}/invoices/INV-001/proposals",
            "headers": {"Idempotency-Key": idempotency_key},
            "body": payload,
            "ts": utc_now(),
        },
    )
    response, body = call(
        client,
        "POST",
        "/invoices/INV-001/proposals",
        headers={"Idempotency-Key": idempotency_key},
        json=payload,
    )
    dump(
        directory / "02-proposal-response.json",
        {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
            "ts": utc_now(),
        },
    )
    steps.append(
        {
            "step": "create_proposal",
            "http_status": response.status_code,
            "status": body.get("status"),
            "blocked_reason": (body.get("blocked_reasons") or [{}])[0].get("code"),
        }
    )

    checks.append(
        check(
            "HTTP 200 for business result", response.status_code == 200, 200, response.status_code
        )
    )
    expected = expected_api(scenario)
    checks.append(
        check(
            "proposal status",
            body.get("status") == expected["status"],
            expected["status"],
            body.get("status"),
        )
    )
    if expected["code"]:
        actual_code = (body.get("blocked_reasons") or [{}])[0].get("code")
        checks.append(
            check(
                "blocked reason code",
                actual_code == expected["code"],
                expected["code"],
                actual_code,
            )
        )

    intent_check = check(
        "customer_intent matches catalog",
        body.get("customer_intent") == scenario["expected_intent"],
        scenario["expected_intent"],
        body.get("customer_intent"),
        critical=scenario_id != "S10",
        note=(
            "S10 fails contract validation before an intent is available; "
            "the rejected 150% value is not exposed by the API."
            if scenario_id == "S10"
            else None
        ),
    )
    checks.append(intent_check)

    if expected["status"] == "PENDING_MERCHANT":
        checks.extend(validate_pending(client, scenario, body, directory))
    else:
        checks.extend(validate_blocked(client, scenario, body, directory))

    if scenario_id != "S12":
        events_response, events = get_events(client, body["proposal_id"])
        dump(
            directory / "08-audit-events.json",
            {"status_code": events_response.status_code, "body": events, "ts": utc_now()},
        )
        actions = [event["action"] for event in events.get("items", [])]
        if expected["status"] != "PENDING_MERCHANT":
            checks.append(
                check(
                    "PROPOSAL_BLOCKED audit event",
                    "PROPOSAL_BLOCKED" in actions,
                    "PROPOSAL_BLOCKED",
                    actions,
                )
            )

    failed_critical = [item for item in checks if item["critical"] and not item["passed"]]
    failed_non_critical = [item for item in checks if not item["critical"] and not item["passed"]]
    if failed_critical:
        status = "FAIL"
    elif failed_non_critical:
        status = "PASS_WITH_OBSERVATION"
    else:
        status = "PASS"

    result = {
        "scenario_id": scenario_id,
        "scenario_name": scenario["id"],
        "category": scenario["category"],
        "catalog_outcome": scenario["expected_outcome"],
        "api_expected_status": expected["status"],
        "api_expected_code": expected["code"],
        "actual_status": body.get("status"),
        "actual_code": (body.get("blocked_reasons") or [{}])[0].get("code"),
        "http_status": response.status_code,
        "status": status,
        "checks": checks,
        "steps": steps,
        "proposal_id": body.get("proposal_id"),
        "executed_at": utc_now(),
        "evidence_dir": f"docs/evidence/F1-23/{scenario_id}",
    }
    dump(directory / "result.json", result)
    return result


def run_seed_validation() -> dict[str, Any]:
    directory = EVIDENCE_ROOT / "SEED"
    checks: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="f1-23-seed-") as temp_dir:
        db_path = Path(temp_dir) / "qa.db"
        client = new_client(db_path)
        try:
            with client:
                health_response, health = call_root(client, "GET", "/health")
                dump(
                    directory / "health.json",
                    {"status_code": health_response.status_code, "body": health, "ts": utc_now()},
                )
                checks.extend(
                    [
                        check(
                            "health HTTP 200",
                            health_response.status_code == 200,
                            200,
                            health_response.status_code,
                        ),
                        check(
                            "health status ok",
                            health.get("status") == "ok",
                            "ok",
                            health.get("status"),
                        ),
                        check(
                            "demo mode enabled",
                            health.get("demo_mode") is True,
                            True,
                            health.get("demo_mode"),
                        ),
                        check(
                            "PayPal mode mock",
                            health.get("paypal_mode") == "mock",
                            "mock",
                            health.get("paypal_mode"),
                        ),
                        check(
                            "agent mode scripted",
                            health.get("agent_mode") == "scripted",
                            "scripted",
                            health.get("agent_mode"),
                        ),
                    ]
                )

                invoices_response, invoices = call(client, "GET", "/invoices")
                dump(
                    directory / "invoices.json",
                    {
                        "status_code": invoices_response.status_code,
                        "body": invoices,
                        "ts": utc_now(),
                    },
                )
                actual = {item["id"]: (item["balance"], item["status"]) for item in invoices}
                checks.extend(
                    [
                        check(
                            "invoices HTTP 200",
                            invoices_response.status_code == 200,
                            200,
                            invoices_response.status_code,
                        ),
                        check(
                            "seed invoice balances and statuses",
                            actual == _SEED_INVOICES,
                            _SEED_INVOICES,
                            actual,
                        ),
                        check(
                            "no customer email leaked",
                            all("email" not in item for item in invoices),
                            True,
                            [item["id"] for item in invoices if "email" in item],
                        ),
                        check(
                            "overdue invoices linked to mock PayPal",
                            all(
                                item["paypal_invoice_id"]
                                for item in invoices
                                if item["status"] == "OVERDUE"
                            ),
                            True,
                            {
                                item["id"]: item["paypal_invoice_id"]
                                for item in invoices
                                if item["status"] == "OVERDUE"
                            },
                        ),
                    ]
                )

                for invoice_id, expected_pair in _SEED_INVOICES.items():
                    detail_response, detail = call(client, "GET", f"/invoices/{invoice_id}")
                    dump(
                        directory / f"invoice-{invoice_id}.json",
                        {
                            "status_code": detail_response.status_code,
                            "body": detail,
                            "ts": utc_now(),
                        },
                    )
                    actual_pair = (detail.get("balance"), detail.get("status"))
                    checks.append(
                        check(
                            f"{invoice_id} detail",
                            detail_response.status_code == 200 and actual_pair == expected_pair,
                            expected_pair,
                            actual_pair,
                        )
                    )

                policy_response, policy = call(client, "GET", "/policy")
                dump(
                    directory / "policy.json",
                    {"status_code": policy_response.status_code, "body": policy, "ts": utc_now()},
                )
                checks.append(
                    check(
                        "policy HTTP 200",
                        policy_response.status_code == 200,
                        200,
                        policy_response.status_code,
                    )
                )
                checks.append(
                    check("policy values", policy == _EXPECTED_POLICY, _EXPECTED_POLICY, policy)
                )
        finally:
            from app.core.db import get_engine

            get_engine().dispose()
            clear_caches()

    failed = [item for item in checks if not item["passed"]]
    result = {
        "scenario_id": "SEED",
        "scenario_name": "Seed and policy data validation",
        "category": "data_integrity",
        "catalog_outcome": "N/A",
        "api_expected_status": "N/A",
        "api_expected_code": None,
        "actual_status": "N/A",
        "actual_code": None,
        "http_status": 200,
        "status": "FAIL" if failed else "PASS",
        "checks": checks,
        "steps": [{"step": "seed_validation", "checks": len(checks)}],
        "proposal_id": None,
        "executed_at": utc_now(),
        "evidence_dir": "docs/evidence/F1-23/SEED",
    }
    dump(directory / "result.json", result)
    return result


def render_matrix(results: list[dict[str, Any]]) -> str:
    lines = [
        "# F1-23 Phase A - Executed Scenario Matrix",
        "",
        f"Generated: {utc_now()}",
        "",
        "Environment: local SQLite, demo seed, `PAYPAL_MODE=mock`, `AGENT_MODE=scripted`.",
        "The API maps the catalog outcome `CLARIFICATION` to `BLOCKED` + "
        "`CLARIFICATION_REQUIRED`, and `INVALID_AGENT_OUTPUT` to `BLOCKED` + "
        "`INVALID_AGENT_OUTPUT` (DEC-05).",
        "",
        "| ID | Scenario | Catalog outcome | API expected | Actual | Status | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        expected = result["api_expected_status"]
        if result["api_expected_code"]:
            expected += f" / `{result['api_expected_code']}`"
        actual = result["actual_status"]
        if result["actual_code"]:
            actual += f" / `{result['actual_code']}`"
        lines.append(
            f"| {result['scenario_id']} | {result['scenario_name']} | "
            f"{result['catalog_outcome']} | {expected} | {actual} | "
            f"**{result['status']}** | `{result['evidence_dir']}` |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- `PASS_WITH_OBSERVATION` means the primary business result is correct but a "
        "non-critical expectation differs; see `F1-23-defects.md`."
    )
    lines.append(
        "- S07 tone quality, S08/S09 real-LLM injection resistance, PayPal Sandbox and UI "
        "are out of scope for this mock/scripted run and are recorded as BLOCKED below."
    )
    lines.append("")
    lines.append("## Blocked items (Phase A)")
    lines.append("")
    lines.append("| ID | Scope | Dependency | Affected validation | Status |")
    lines.append("|---|---|---|---|---|")
    for item in _BLOCKED_ITEMS:
        lines.append("| {id} | {scope} | {dependency} | {affected} | **{status}** |".format(**item))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    QA_ROOT.mkdir(parents=True, exist_ok=True)

    environment = {
        "generated_at": utc_now(),
        "python": sys.version,
        "platform": sys.platform,
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "settings": {
            "APP_ENV": "local",
            "DEMO_MODE": "true",
            "PAYPAL_MODE": "mock",
            "AGENT_MODE": "scripted",
            "ALLOW_SCENARIO_ID": "true",
            "ALLOW_SANDBOX_PAYMENT_SHORTCUT": "false",
            "DATABASE_URL": "temporary SQLite per scenario",
            "PUBLIC_BASE_URL": "http://localhost:8000",
        },
    }
    dump(EVIDENCE_ROOT / "environment.json", environment)

    results: list[dict[str, Any]] = [run_seed_validation()]
    for scenario in scenarios:
        scenario_id = scenario["id"].split("_", 1)[0]
        directory = EVIDENCE_ROOT / scenario_id
        with tempfile.TemporaryDirectory(prefix=f"f1-23-{scenario_id.lower()}-") as temp_dir:
            db_path = Path(temp_dir) / "qa.db"
            client = new_client(db_path)
            try:
                with client:
                    result = execute_scenario(client, scenario, directory)
            except Exception as exc:
                result = {
                    "scenario_id": scenario_id,
                    "scenario_name": scenario["id"],
                    "category": scenario["category"],
                    "catalog_outcome": scenario["expected_outcome"],
                    "api_expected_status": expected_api(scenario)["status"],
                    "api_expected_code": expected_api(scenario)["code"],
                    "actual_status": "ERROR",
                    "actual_code": None,
                    "http_status": None,
                    "status": "FAIL",
                    "checks": [
                        check(
                            "scenario execution", False, "completed", f"{type(exc).__name__}: {exc}"
                        )
                    ],
                    "steps": [],
                    "proposal_id": None,
                    "executed_at": utc_now(),
                    "evidence_dir": f"docs/evidence/F1-23/{scenario_id}",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                dump(directory / "result.json", result)
            finally:
                from app.core.db import get_engine

                get_engine().dispose()
                clear_caches()
        results.append(result)
        print(f"{result['scenario_id']}: {result['status']}")

    summary = {
        "generated_at": utc_now(),
        "environment": environment,
        "results": results,
        "blocked_items": _BLOCKED_ITEMS,
        "totals": {
            "scenarios": len(scenarios),
            "evidence_entries": len(results),
            "pass": sum(1 for result in results if result["status"] == "PASS"),
            "pass_with_observation": sum(
                1 for result in results if result["status"] == "PASS_WITH_OBSERVATION"
            ),
            "fail": sum(1 for result in results if result["status"] == "FAIL"),
            "blocked": sum(1 for result in results if result["status"] == "BLOCKED"),
        },
    }
    dump(EVIDENCE_ROOT / "run-summary.json", summary)
    (QA_ROOT / "F1-23-phase-a-matrix.md").write_text(render_matrix(results), encoding="utf-8")
    print(json.dumps(summary["totals"], indent=2))
    return 0 if summary["totals"]["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
