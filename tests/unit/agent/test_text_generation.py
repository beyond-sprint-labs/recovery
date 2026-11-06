"""Unit tests for F1-06 financial text generation."""

import json

import pytest

from app.agent.agent import RecoveryAgent
from app.agent.mock_llm_client import MockLLMClient
from app.agent.mock_text_llm_client import MockTextLLMClient
from app.finance.engine import build_alternatives, calculate_alternatives


class RecordingTextClient:
    """Record text-generation calls without a real LLM."""

    def __init__(self):
        self.calls = []

    def generate_text(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return "Draft generated for backend validation."


@pytest.fixture
def engine_result():
    """Two approved alternatives with deterministic figures."""

    return {
        "engine_version": "1.0.0",
        "alternatives": [
            {
                "type": "settlement_discount",
                "terms": {"discount_pct": "10"},
                "amount_due_now": "900.00",
                "installment_amount": None,
                "total_paid": "900.00",
                "policy_ok": True,
                "schedule": [{"amount": "900.00"}],
            },
            {
                "type": "down_payment_installments",
                "terms": {"installments": 3},
                "amount_due_now": "300.00",
                "installment_amount": "240.37",
                "total_paid": "1021.10",
                "policy_ok": True,
                "schedule": [
                    {"amount": "300.00"},
                    {"amount": "240.37"},
                    {"amount": "240.37"},
                    {"amount": "240.36"},
                ],
            },
        ],
    }


def test_explanation_uses_approved_financial_figures(engine_result):
    text_client = RecordingTextClient()
    agent = RecoveryAgent(MockLLMClient(), text_client)

    result = agent.explain_alternatives(engine_result)

    assert result == "Draft generated for backend validation."
    assert len(text_client.calls) == 1

    system_prompt, user_payload = text_client.calls[0]
    payload = json.loads(user_payload)

    assert "Option A" in system_prompt
    assert payload["alternatives"][0]["amount_due_now"] == "900.00"
    assert payload["alternatives"][1]["installment_amount"] == "240.37"
    assert payload["alternatives"][1]["final_installment_amount"] == "240.36"


def test_customer_message_uses_official_prompt(engine_result):
    text_client = RecordingTextClient()
    agent = RecoveryAgent(MockLLMClient(), text_client)

    result = agent.draft_customer_message(engine_result)

    assert result == "Draft generated for backend validation."
    assert len(text_client.calls) == 1
    assert "Greet the customer" in text_client.calls[0][0]


def test_blocked_alternative_prevents_generation(engine_result):
    text_client = RecordingTextClient()
    agent = RecoveryAgent(MockLLMClient(), text_client)

    engine_result["alternatives"][0]["policy_ok"] = False

    with pytest.raises(ValueError, match="blocked"):
        agent.explain_alternatives(engine_result)

    assert text_client.calls == []


def test_missing_text_client_raises_error(engine_result):
    agent = RecoveryAgent(MockLLMClient())

    with pytest.raises(RuntimeError, match="not configured"):
        agent.explain_alternatives(engine_result)


def test_missing_financial_figures_prevents_generation(engine_result):
    text_client = RecordingTextClient()
    agent = RecoveryAgent(MockLLMClient(), text_client)

    engine_result["alternatives"][1]["total_paid"] = None

    with pytest.raises(ValueError, match="Missing required"):
        agent.draft_customer_message(engine_result)

    assert text_client.calls == []


def test_mock_text_client_generates_exact_financial_figures(engine_result):
    """Demo drafts must preserve the engine-provided figures."""
    agent = RecoveryAgent(
        client=MockLLMClient(),
        text_client=MockTextLLMClient(),
    )

    explanation = agent.explain_alternatives(engine_result)
    customer_draft = agent.draft_customer_message(engine_result)

    for text in (explanation, customer_draft):
        assert "$900.00" in text
        assert "10% discount" in text
        assert "$300.00" in text
        assert "3 monthly installments" in text
        assert "$240.37" in text
        assert "$240.36" in text
        assert "$1021.10" in text

    assert explanation.startswith("Option A:")
    assert customer_draft.startswith("Hello,")


def test_mock_text_client_is_deterministic(engine_result):
    """Identical inputs must produce identical drafts."""
    agent = RecoveryAgent(
        client=MockLLMClient(),
        text_client=MockTextLLMClient(),
    )

    first = agent.explain_alternatives(engine_result)
    second = agent.explain_alternatives(engine_result)

    assert first == second


def test_mock_text_client_rejects_unsupported_prompt():
    """Unknown prompts must not generate text."""
    client = MockTextLLMClient()

    payload = {
        "alternatives": [
            {
                "type": "settlement_discount",
                "amount_due_now": "900.00",
                "discount_pct": "10",
            },
            {
                "type": "down_payment_installments",
                "amount_due_now": "300.00",
                "installments": 3,
                "installment_amount": "240.37",
                "final_installment_amount": "240.36",
                "total_paid": "1021.10",
            },
        ]
    }

    with pytest.raises(ValueError, match="Unsupported"):
        client.generate_text(
            system="Unknown prompt",
            user=json.dumps(payload),
        )


def test_real_finance_engine_generates_consistent_drafts():
    """Drafts must use figures calculated by the actual engine."""

    request = {
        "engine_version": "1.0.0",
        "invoice": {
            "id": "INV-001",
            "currency": "USD",
            "balance": "1000.00",
            "due_date": "2026-10-15",
            "as_of_date": "2026-11-11",
        },
        "alternatives": [
            {
                "type": "settlement_discount",
                "discount_pct": "10",
            },
            {
                "type": "down_payment_installments",
                "down_payment_pct": "30",
                "installments": 3,
                "periodic_rate_pct": "1.5",
            },
        ],
        "policy": {
            "max_discount_pct": "15",
            "min_down_payment_pct": "20",
            "max_installments": 6,
            "max_financing_rate_pct": "2.0",
            "merchant_discount_rate_pct": "1.0",
        },
    }

    result = calculate_alternatives(request)

    assert len(result["alternatives"]) == 2
    assert all(alternative["policy_ok"] for alternative in result["alternatives"])

    agent = RecoveryAgent(
        client=MockLLMClient(),
        text_client=MockTextLLMClient(),
    )

    explanation = agent.explain_alternatives(result)
    customer_draft = agent.draft_customer_message(result)

    settlement, installments = result["alternatives"]

    for text in (explanation, customer_draft):
        assert f"${settlement['amount_due_now']}" in text
        assert f"${installments['amount_due_now']}" in text
        assert f"${installments['installment_amount']}" in text
        assert f"${installments['total_paid']}" in text
        assert f"${installments['schedule'][-1]['amount']}" in text


def test_real_finance_policy_blocks_unauthorized_drafts():
    """A policy violation must prevent financial text generation."""

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
        settlement_terms={"discount_pct": "40"},
        installment_terms={
            "down_payment_pct": "30",
            "installments": 3,
            "periodic_rate_pct": "1.5",
        },
    )

    assert alternatives[0]["policy_ok"] is False
    assert alternatives[1]["policy_ok"] is True

    engine_result = {
        "engine_version": "1.0.0",
        "alternatives": alternatives,
    }

    text_client = RecordingTextClient()
    agent = RecoveryAgent(
        client=MockLLMClient(),
        text_client=text_client,
    )

    with pytest.raises(ValueError, match="blocked"):
        agent.explain_alternatives(engine_result)

    with pytest.raises(ValueError, match="blocked"):
        agent.draft_customer_message(engine_result)

    assert text_client.calls == []
