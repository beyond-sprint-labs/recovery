"""Recovery F1-06 agent orchestration."""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from app.agent.intent_extractor import extract_intent
from app.agent.llm_client import LLMClient
from app.core.schemas import CustomerIntent

# The backend owns invoice balance, dates, policy, and calculations.
# Replace object with EngineResult when its shared type is available.
ToolRunner = Callable[[CustomerIntent], object]


class AgentOutput(BaseModel):
    """Structured agent output agreed with the backend."""

    model_config = ConfigDict(extra="forbid")

    intent: CustomerIntent
    explanation: str | None = None
    customer_message_draft: str | None = None


class RecoveryAgent:
    """Extract intent and delegate financial calculations."""

    def __init__(self, client: LLMClient):
        self.client = client

    def run(
        self,
        message: str,
        tool_runner: ToolRunner,
    ) -> AgentOutput:
        """Process a server-sanitized customer message."""

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

        # The backend supplies all financial context.
        # Result handling and drafting belong to the next stage.
        tool_runner(intent)

        return AgentOutput(intent=intent)
