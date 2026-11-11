"""Safe deterministic fallback for the real Recovery LLM agent."""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from app.agent.agent import NegotiationAgent, ToolRunner
from app.agent.errors import InvalidAgentOutputError, LLMUnavailableError
from app.agent.mock_agent import ScriptedAgent
from app.agent.schemas import AgentOutput

_RECOVERABLE_ERRORS = (LLMUnavailableError, InvalidAgentOutputError)


@runtime_checkable
class FallbackReporter(Protocol):
    """An agent that reports deterministic fallback stages and reasons."""

    @property
    def fallback_reasons(self) -> Mapping[str, str]: ...


class FallbackAgent:
    """Use a scripted agent when the LLM cannot produce valid output."""

    def __init__(
        self,
        primary: NegotiationAgent,
        scenario_id: str | None = None,
    ) -> None:
        self._primary = primary
        self._scripted = ScriptedAgent(scenario_id)
        self._reasons: dict[str, str] = {}

    @property
    def fallback_reasons(self) -> Mapping[str, str]:
        """Return safe reason codes for each fallback stage."""
        return dict(self._reasons)

    @property
    def fallback_stages(self) -> frozenset[str]:
        return frozenset(self._reasons)

    @property
    def fallback_used(self) -> bool:
        return bool(self._reasons)

    def _mark_fallback(self, stage: str, error: Exception) -> None:
        reason = error.reason if isinstance(error, LLMUnavailableError) else "INVALID_OUTPUT"
        self._reasons[stage] = reason

    def run(
        self,
        sanitized_message: str,
        tool_runner: ToolRunner,
    ) -> AgentOutput:
        """Fall back during extraction without repeating financial tools."""
        tool_invoked = False

        def guarded_tool_runner(intent):
            nonlocal tool_invoked
            tool_invoked = True
            return tool_runner(intent)

        try:
            output = self._primary.run(
                sanitized_message,
                guarded_tool_runner,
            )
            return AgentOutput.model_validate(output)
        except _RECOVERABLE_ERRORS as error:
            if tool_invoked:
                # Never replay an already invoked financial tool.
                raise

            self._mark_fallback("intent", error)
            return self._scripted.run(
                sanitized_message,
                tool_runner,
            )

    def explain_alternatives(
        self,
        engine_result: Mapping[str, object],
    ) -> str:
        """Use a deterministic explanation if LLM generation fails."""
        try:
            return self._primary.explain_alternatives(engine_result)
        except _RECOVERABLE_ERRORS as error:
            self._mark_fallback("explanation", error)
            return self._scripted.explain_alternatives(engine_result)

    def draft_customer_message(
        self,
        engine_result: Mapping[str, object],
    ) -> str:
        """Use a deterministic customer draft if LLM generation fails."""
        try:
            return self._primary.draft_customer_message(engine_result)
        except _RECOVERABLE_ERRORS as error:
            self._mark_fallback("customer_message", error)
            return self._scripted.draft_customer_message(engine_result)
