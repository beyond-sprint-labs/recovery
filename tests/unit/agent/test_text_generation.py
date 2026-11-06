"""Unit tests for F1-06 financial text generation."""

import json

import pytest

from app.agent.agent import RecoveryAgent
from app.agent.mock_llm_client import MockLLMClient


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
