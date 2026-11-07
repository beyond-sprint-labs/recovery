"""Structured customer intent extraction for Recovery F1-06."""

from app.agent.errors import AgentInputError, InvalidAgentOutputError
from app.agent.llm_client import LLMClient
from app.agent.prompt_loader import load_prompt
from app.core.schemas import CustomerIntent


def extract_intent(
    message: str,
    client: LLMClient,
) -> CustomerIntent:
    """Extract intent from an already sanitized customer message."""

    if not isinstance(message, str):
        raise AgentInputError("Customer message must be a string")

    if not message.strip():
        raise AgentInputError("Customer message cannot be empty")

    response = client.complete(
        system=load_prompt("system_agent.txt"),
        user=message,
        schema=CustomerIntent,
    )

    if not isinstance(response, CustomerIntent):
        raise InvalidAgentOutputError("LLM client returned an invalid response type")

    return response
