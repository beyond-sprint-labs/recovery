"""Deterministic scenario-driven agent for Recovery demo mode."""

from collections.abc import Mapping
from typing import Final

from pydantic import ValidationError

from app.agent.agent import NegotiationAgent, ToolRunner
from app.agent.errors import InvalidAgentOutputError
from app.agent.mock_llm_client import MockLLMClient
from app.agent.mock_text_llm_client import MockTextLLMClient
from app.agent.schemas import AgentOutput
from app.core.schemas import CustomerIntent

# These inputs match the official tests/scenarios/scenarios.json.
# S10 intentionally violates the CustomerIntent percentage contract.
_SCENARIO_INTENTS: Final[Mapping[str, Mapping[str, object]]] = {
    "S01": {"available_now": "300.00", "preferred_installments": 3},
    "S02": {"preferred_installments": 3},
    "S03": {"requested_discount_pct": "40"},
    "S04": {"requested_discount_pct": "10"},
    "S05": {},
    "S06": {},
    "S07": {},
    "S08": {},
    "S09": {},
    "S10": {"requested_discount_pct": "150"},
    "S11": {"preferred_installments": 3},
    "S12": {"requested_discount_pct": "40"},
}

_TAMPERED_SCENARIO: Final = "S11"
_TAMPERED_SENTENCE: Final = " Special year-end total: $850.00."


def scenario_key(scenario_id: str | None) -> str | None:
    """Accept both S03 and S03_exceeds_discount."""
    if scenario_id is None:
        return None
    return scenario_id.split("_", 1)[0].upper()


class ScriptedAgent:
    """Backend-compatible scripted agent for deterministic demos."""

    def __init__(self, scenario_id: str | None = None) -> None:
        self._key = scenario_key(scenario_id)
        self._texts = NegotiationAgent(
            client=MockLLMClient(),
            text_client=MockTextLLMClient(),
        )

    def run(
        self,
        sanitized_message: str,
        tool_runner: ToolRunner,
    ) -> AgentOutput:
        """Extract predefined intent without executing external LLM calls."""
        if self._key is None:
            raw: Mapping[str, object] = {}
        elif self._key in _SCENARIO_INTENTS:
            raw = _SCENARIO_INTENTS[self._key]
        else:
            raise InvalidAgentOutputError("Unknown demo scenario")

        try:
            intent = CustomerIntent.model_validate(raw)
        except ValidationError as error:
            raise InvalidAgentOutputError("Scripted intent failed contract validation") from error

        if intent.model_dump(exclude_none=True):
            # The backend owns all calculations and policy enforcement.
            # The runner may raise; its authoritative result is not owned here.
            tool_runner(intent)

        return AgentOutput(intent=intent)

    def explain_alternatives(self, engine_result: Mapping[str, object]) -> str:
        """Generate a deterministic merchant-facing explanation."""
        text = self._texts.explain_alternatives(engine_result)

        if self._key == _TAMPERED_SCENARIO:
            return text + _TAMPERED_SENTENCE

        return text

    def draft_customer_message(
        self,
        engine_result: Mapping[str, object],
    ) -> str:
        """Generate a deterministic customer-facing message."""
        return self._texts.draft_customer_message(engine_result)
