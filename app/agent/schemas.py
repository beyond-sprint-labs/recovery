"""Shared output contract for the F1-06 negotiation agent."""

from pydantic import BaseModel, ConfigDict

from app.core.schemas import CustomerIntent


class AgentOutput(BaseModel):
    """Structured output shared with RecoveryService."""

    model_config = ConfigDict(extra="forbid")

    intent: CustomerIntent
    explanation: str | None = None
    customer_message_draft: str | None = None
