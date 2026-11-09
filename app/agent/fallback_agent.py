"""Safe deterministic fallback for the real Recovery LLM agent."""

from collections.abc import Mapping

from app.agent.agent import NegotiationAgent, ToolRunner
from app.agent.errors import InvalidAgentOutputError, LLMUnavailableError
from app.agent.mock_agent import ScriptedAgent
from app.agent.schemas import AgentOutput

_RECOVERABLE_ERRORS = (LLMUnavailableError, InvalidAgentOutputError)


class FallbackAgent:
    """Use a scripted agent when the LLM provider cannot produce valid output."""

    def __init__(
        self,
        primary: NegotiationAgent,
        scenario_id: str | None = None,
    ) -> None:
        self._primary = primary
        self._scripted = ScriptedAgent(scenario_id)
        self.fallback_used = False
        self.fallback_stages: set[str] = set()

    def _mark_fallback(self, stage: str) -> None:
        """Store a safe marker, never provider errors or credentials."""
        self.fallback_used = True
        self.fallback_stages.add(stage)

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
        except _RECOVERABLE_ERRORS:
            if tool_invoked:
                # An error after tool execution must not replay the tool.
                raise

            self._mark_fallback("intent")
            return self._scripted.run(
                sanitized_message,
                tool_runner,
            )

    def explain_alternatives(
        self,
        engine_result: Mapping[str, object],
    ) -> str:
        """Use deterministic explanation if LLM generation fails."""
        try:
            return self._primary.explain_alternatives(engine_result)
        except _RECOVERABLE_ERRORS:
            self._mark_fallback("explanation")
            return self._scripted.explain_alternatives(engine_result)

    def draft_customer_message(
        self,
        engine_result: Mapping[str, object],
    ) -> str:
        """Use deterministic customer draft if LLM generation fails."""
        try:
            return self._primary.draft_customer_message(engine_result)
        except _RECOVERABLE_ERRORS:
            self._mark_fallback("customer_message")
            return self._scripted.draft_customer_message(engine_result)
