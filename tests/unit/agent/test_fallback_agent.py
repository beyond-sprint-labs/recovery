"""Regression tests for F1-20 deterministic agent fallback."""

from unittest.mock import Mock

import pytest

from app.agent.agent import AgentOutput
from app.agent.errors import InvalidAgentOutputError, LLMUnavailableError
from app.agent.fallback_agent import FallbackAgent
from app.core.schemas import CustomerIntent


def test_successful_primary_agent_does_not_fallback():
    intent = CustomerIntent(preferred_installments=3)
    primary = Mock()
    primary.run.return_value = AgentOutput(intent=intent)
    agent = FallbackAgent(primary)

    output = agent.run("Three installments", lambda _: None)

    assert output.intent == intent
    assert agent.fallback_used is False
    assert agent.fallback_stages == set()


@pytest.mark.parametrize(
    "failure",
    [
        LLMUnavailableError("Provider unavailable"),
        InvalidAgentOutputError("Invalid response"),
    ],
)
def test_intent_failure_activates_scripted_fallback(failure):
    primary = Mock()
    primary.run.side_effect = failure
    agent = FallbackAgent(primary, scenario_id="S01")
    received = []

    output = agent.run("Payment request", received.append)

    assert output.intent.preferred_installments == 3
    assert output.intent.available_now == "300.00"
    assert received == [output.intent]
    assert agent.fallback_used is True
    assert agent.fallback_stages == {"intent"}


def test_no_scenario_fallback_requests_clarification():
    primary = Mock()
    primary.run.side_effect = LLMUnavailableError("Timeout")
    agent = FallbackAgent(primary)

    calls = []
    output = agent.run("Payment request", calls.append)

    assert output.intent == CustomerIntent()
    assert calls == []
    assert agent.fallback_used is True


def test_finance_failure_is_not_hidden():
    primary = Mock()

    def run_with_finance_failure(message, runner):
        runner(CustomerIntent(preferred_installments=3))

    primary.run.side_effect = run_with_finance_failure
    agent = FallbackAgent(primary, scenario_id="S01")

    def failing_runner(intent):
        raise RuntimeError("Finance error")

    with pytest.raises(RuntimeError, match="Finance error"):
        agent.run("Payment request", failing_runner)

    assert agent.fallback_used is False


def test_tool_is_not_replayed_after_provider_failure():
    primary = Mock()

    def run_then_fail(message, runner):
        runner(CustomerIntent(preferred_installments=3))
        raise LLMUnavailableError("Provider unavailable")

    primary.run.side_effect = run_then_fail
    agent = FallbackAgent(primary, scenario_id="S01")
    calls = []

    with pytest.raises(LLMUnavailableError):
        agent.run("Payment request", calls.append)

    assert len(calls) == 1
    assert agent.fallback_used is False


def test_explanation_failure_uses_scripted_text():
    primary = Mock()
    primary.explain_alternatives.side_effect = LLMUnavailableError("Provider unavailable")
    agent = FallbackAgent(primary)
    agent._scripted.explain_alternatives = Mock(return_value="Approved alternatives are available.")

    engine_result = {"alternatives": []}
    text = agent.explain_alternatives(engine_result)

    assert text == "Approved alternatives are available."
    assert agent.fallback_used is True
    assert agent.fallback_stages == {"explanation"}
    agent._scripted.explain_alternatives.assert_called_once_with(engine_result)


def test_customer_draft_failure_uses_scripted_text():
    primary = Mock()
    primary.draft_customer_message.side_effect = InvalidAgentOutputError("Invalid LLM output")
    agent = FallbackAgent(primary)
    agent._scripted.draft_customer_message = Mock(
        return_value="Please review the proposed payment options."
    )

    engine_result = {"alternatives": []}
    text = agent.draft_customer_message(engine_result)

    assert text == "Please review the proposed payment options."
    assert agent.fallback_used is True
    assert agent.fallback_stages == {"customer_message"}
    agent._scripted.draft_customer_message.assert_called_once_with(engine_result)


def test_unexpected_text_error_is_not_hidden():
    primary = Mock()
    primary.explain_alternatives.side_effect = RuntimeError("Unexpected internal failure")
    agent = FallbackAgent(primary)

    with pytest.raises(RuntimeError, match="Unexpected internal failure"):
        agent.explain_alternatives({"alternatives": []})

    assert agent.fallback_used is False


def test_fallback_reason_codes_are_recorded_per_stage():
    """Record safe reason codes for each fallback stage."""
    from unittest.mock import Mock

    primary = Mock()
    primary.run.side_effect = LLMUnavailableError(
        "rejected",
        reason="PROVIDER_REJECTED",
    )
    primary.explain_alternatives.side_effect = InvalidAgentOutputError("bad output")

    agent = FallbackAgent(primary)
    agent._scripted.explain_alternatives = Mock(return_value="Approved alternatives.")

    agent.run("Payment request", lambda _: None)
    agent.explain_alternatives({"alternatives": []})

    assert agent.fallback_reasons == {
        "intent": "PROVIDER_REJECTED",
        "explanation": "INVALID_OUTPUT",
    }
