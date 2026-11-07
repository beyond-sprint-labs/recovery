"""Integration tests for F1-06 agent and F1-14b Text Guard."""

from decimal import Decimal

import pytest

from app.agent.mock_agent import ScriptedAgent
from app.finance.engine import build_alternatives
from app.services.text_guard import AllowedNumbers, check_text_numbers


@pytest.fixture
def engine_result():
    """Generate approved alternatives using the real financial engine."""
    policy = {
        "currency": "USD",
        "max_discount_pct": "15",
        "min_down_payment_pct": "20",
        "max_installments": 6,
        "max_financing_rate_pct": "2.0",
        "merchant_discount_rate_pct": "1.0",
    }

    alternatives = build_alternatives(
        balance="1000.00",
        pivot_date="2026-11-11",
        policy=policy,
        settlement_terms={"discount_pct": "10"},
        installment_terms={
            "down_payment_pct": "30",
            "installments": 3,
            "periodic_rate_pct": "1.5",
        },
    )

    assert len(alternatives) == 2
    assert all(alt["policy_ok"] for alt in alternatives)

    return {
        "engine_version": "1.0.0",
        "alternatives": alternatives,
    }


def allowed_from_engine(engine_result):
    """Allow only numeric figures authorized for the generated drafts."""
    values = set()

    for alternative in engine_result["alternatives"]:
        values.add(Decimal(alternative["amount_due_now"]))
        values.add(Decimal(alternative["total_paid"]))

        if alternative["installment_amount"] is not None:
            values.add(Decimal(alternative["installment_amount"]))

        for item in alternative["schedule"]:
            values.add(Decimal(item["amount"]))

        terms = alternative["terms"]

        if alternative["type"] == "settlement_discount":
            values.add(Decimal(terms["discount_pct"]))
        else:
            values.add(Decimal(terms["installments"]))

    return AllowedNumbers(values=frozenset(values))


def test_authorized_agent_text_passes_guard(engine_result):
    """Genuine engine figures must pass the real Text Guard."""
    agent = ScriptedAgent("S01_partial_payment_now")

    explanation = agent.explain_alternatives(engine_result)
    customer_draft = agent.draft_customer_message(engine_result)

    allowed = allowed_from_engine(engine_result)
    result = check_text_numbers(
        [explanation, customer_draft],
        allowed,
    )

    assert result.status == "PASSED"
    assert result.unmatched == []


def test_s11_tampered_text_fails_guard(engine_result):
    """S11 must expose the unauthorized amount to Text Guard."""
    agent = ScriptedAgent("S11_text_mismatch")

    explanation = agent.explain_alternatives(engine_result)
    customer_draft = agent.draft_customer_message(engine_result)

    assert "$850.00" in explanation

    allowed = allowed_from_engine(engine_result)
    assert Decimal("850.00") not in allowed.values

    result = check_text_numbers(
        [explanation, customer_draft],
        allowed,
    )

    assert result.status == "FAILED"
    assert result.unmatched == ["850.00"]
