"""Tests for the initial Recovery agent orchestration."""

import pytest

from app.agent.agent import RecoveryAgent
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
    agent = RecoveryAgent(FakeLLMClient(intent))
    received = []

    def fake_tool_runner(customer_intent):
        received.append(customer_intent)
        return {"status": "SIMULATED"}

    output = agent.run(
        "I can pay $300 in three installments",
        fake_tool_runner,
    )

    assert output.intent == intent
    assert output.tool_result == {"status": "SIMULATED"}
    assert received == [intent]


def test_agent_does_not_call_tool_for_empty_intent():
    agent = RecoveryAgent(FakeLLMClient(CustomerIntent()))
    calls = []

    def fake_tool_runner(intent):
        calls.append(intent)
        return {"status": "SIMULATED"}

    output = agent.run("Hello", fake_tool_runner)

    assert output.intent == CustomerIntent()
    assert output.tool_result is None
    assert calls == []


def test_agent_passes_excessive_discount_to_backend():
    intent = CustomerIntent(requested_discount_pct="40")
    agent = RecoveryAgent(FakeLLMClient(intent))
    received = []

    def fake_tool_runner(customer_intent):
        received.append(customer_intent)
        return {"status": "BLOCKED"}

    output = agent.run(
        "Can I get a 40% discount?",
        fake_tool_runner,
    )

    assert received[0].requested_discount_pct == "40"
    assert output.tool_result["status"] == "BLOCKED"


def test_agent_propagates_finance_engine_failure():
    """Financial tool failures must never become fake approvals."""
    intent = CustomerIntent(available_now="300.00")
    agent = RecoveryAgent(FakeLLMClient(intent))

    def failing_tool_runner(customer_intent):
        raise RuntimeError("Finance engine unavailable")

    with pytest.raises(RuntimeError, match="Finance engine unavailable"):
        agent.run("I can pay $300 today", failing_tool_runner)


def test_agent_does_not_call_tool_for_greeting():
    """Messages without payment intent must not trigger tools."""
    agent = RecoveryAgent(FakeLLMClient(CustomerIntent()))

    def forbidden_tool_runner(customer_intent):
        pytest.fail("tool_runner must not be called")

    output = agent.run("Hello, good morning", forbidden_tool_runner)

    assert output.intent == CustomerIntent()
    assert output.tool_result is None
