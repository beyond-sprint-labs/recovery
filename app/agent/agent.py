"""Initial orchestration for Recovery F1-06."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agent.intent_extractor import extract_intent
from app.agent.llm_client import LLMClient
from app.core.schemas import CustomerIntent

# Provisional contract: confirm with F1-13 owner.
ToolRunner = Callable[[CustomerIntent], dict[str, Any]]


class AgentOutput(BaseModel):
    """Provisional structured agent result."""

    model_config = ConfigDict(extra="forbid")

    intent: CustomerIntent
    tool_result: dict[str, Any] | None = None


class RecoveryAgent:
    """Extract customer intent and delegate financial work."""

    def __init__(self, client: LLMClient):
        self.client = client

    def run(
        self,
        message: str,
        tool_runner: ToolRunner,
    ) -> AgentOutput:
        """Run the agent without calculating financial figures."""

        intent = extract_intent(message, self.client)

        has_intent = any(
            value is not None
            for value in (
                intent.available_now,
                intent.preferred_installments,
                intent.requested_discount_pct,
                intent.desired_date,
            )
        )

        if not has_intent:
            return AgentOutput(intent=intent)

        result = tool_runner(intent)

        return AgentOutput(
            intent=intent,
            tool_result=result,
        )
