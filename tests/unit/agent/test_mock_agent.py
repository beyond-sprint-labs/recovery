"""Regression tests for the F1-06 scripted demo agent."""

import json
from pathlib import Path

import pytest

from app.agent.errors import InvalidAgentOutputError
from app.agent.mock_agent import ScriptedAgent, scenario_key

SCENARIOS_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "scenarios.json"

SCENARIOS = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]


@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=lambda scenario: scenario["id"],
)
def test_scripted_agent_matches_official_scenario(scenario):
    """The scripted agent must reproduce the official intent contract."""
    calls = []
    agent = ScriptedAgent(scenario_id=scenario["id"])

    if scenario["id"].startswith("S10"):
        with pytest.raises(InvalidAgentOutputError):
            agent.run(
                sanitized_message=scenario["customer_message"],
                tool_runner=lambda intent: calls.append(intent),
            )

        assert calls == []
        return

    output = agent.run(
        sanitized_message=scenario["customer_message"],
        tool_runner=lambda intent: calls.append(intent),
    )

    actual = output.intent.model_dump(mode="json")
    assert actual == scenario["expected_intent"]

    has_intent = any(value is not None for value in actual.values())
    assert len(calls) == int(has_intent)


def test_scenario_key_supports_short_and_full_ids():
    assert scenario_key("S03") == "S03"
    assert scenario_key("S03_exceeds_discount") == "S03"


def test_unknown_scenario_is_rejected():
    agent = ScriptedAgent(scenario_id="S99")

    with pytest.raises(InvalidAgentOutputError):
        agent.run(
            sanitized_message="Any message",
            tool_runner=lambda intent: None,
        )


@pytest.mark.parametrize(
    "message",
    [
        "Hello, I need help with my invoice.",
        "I cannot pay the full amount right now.",
    ],
)
def test_no_scenario_returns_empty_intent_without_tools(message):
    """Free-text demo mode must request clarification, not fail critically."""
    agent = ScriptedAgent(scenario_id=None)

    def forbidden_tool_runner(intent):
        pytest.fail("Financial tools must not run without a scenario")

    output = agent.run(
        sanitized_message=message,
        tool_runner=forbidden_tool_runner,
    )

    assert output.intent.model_dump(exclude_none=True) == {}
    assert output.explanation is None
    assert output.customer_message_draft is None
