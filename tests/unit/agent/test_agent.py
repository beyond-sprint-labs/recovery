"""Tests for Recovery F1-06 agent orchestration."""

import pytest

from app.agent.agent import AgentOutput, NegotiationAgent
from app.core.schemas import CustomerIntent


class FakeLLMClient:
    def __init__(self, intent: CustomerIntent):
        self.intent = intent

    def complete(self, system, user, schema):
        return self.intent


def test_agent_calls_tool_for_valid_intent():
    intent = CustomerIntent(
        available_now="300.00",
        preferred_installments=3,
    )
    agent = NegotiationAgent(FakeLLMClient(intent))
    received = []

    def fake_tool_runner(customer_intent):
        received.append(customer_intent)
        return {"status": "SIMULATED"}

    output = agent.run(
        "I can pay $300 in three installments",
        fake_tool_runner,
    )

    assert isinstance(output, AgentOutput)
    assert output.intent == intent
    assert output.explanation is None
    assert output.customer_message_draft is None
    assert received == [intent]


def test_agent_does_not_call_tool_for_empty_intent():
    agent = NegotiationAgent(FakeLLMClient(CustomerIntent()))
    calls = []

    def fake_tool_runner(intent):
        calls.append(intent)
        return {"status": "SIMULATED"}

    output = agent.run("Hello", fake_tool_runner)

    assert output.intent == CustomerIntent()
    assert output.explanation is None
    assert output.customer_message_draft is None
    assert calls == []


def test_agent_passes_excessive_discount_to_backend():
    intent = CustomerIntent(requested_discount_pct="40")
    agent = NegotiationAgent(FakeLLMClient(intent))
    received = []

    def fake_tool_runner(customer_intent):
        received.append(customer_intent)
        return {"status": "BLOCKED"}

    output = agent.run(
        "Can I get a 40% discount?",
        fake_tool_runner,
    )

    assert received == [intent]
    assert output.intent.requested_discount_pct == "40"
    assert output.explanation is None
    assert output.customer_message_draft is None


def test_agent_propagates_finance_engine_failure():
    intent = CustomerIntent(available_now="300.00")
    agent = NegotiationAgent(FakeLLMClient(intent))

    def failing_tool_runner(customer_intent):
        raise RuntimeError("Finance engine unavailable")

    with pytest.raises(RuntimeError, match="Finance engine unavailable"):
        agent.run("I can pay $300 today", failing_tool_runner)


def test_agent_does_not_call_tool_for_greeting():
    agent = NegotiationAgent(FakeLLMClient(CustomerIntent()))

    def forbidden_tool_runner(customer_intent):
        pytest.fail("tool_runner must not be called")

    output = agent.run("Hello, good morning", forbidden_tool_runner)

    assert output.intent == CustomerIntent()
    assert output.explanation is None
    assert output.customer_message_draft is None


def test_agent_delegates_only_customer_intent():
    """F1-06 must not supply server-owned financial context."""
    intent = CustomerIntent(
        available_now="300.00",
        preferred_installments=3,
    )

    agent = NegotiationAgent(FakeLLMClient(intent))
    received = []

    def fake_tool_runner(requested_terms):
        received.append(requested_terms)
        return {
            "engine_version": "1.0.0",
            "alternatives": [],
        }

    output = agent.run(
        "I can pay $300 in three installments",
        fake_tool_runner,
    )

    assert received == [intent]
    assert isinstance(received[0], CustomerIntent)

    assert set(received[0].model_dump()) == {
        "available_now",
        "preferred_installments",
        "requested_discount_pct",
        "desired_date",
    }

    assert output.intent == intent
    assert output.explanation is None
    assert output.customer_message_draft is None
