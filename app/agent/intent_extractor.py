"""Structured customer intent extraction for Recovery F1-06."""

from typing import Final

from app.agent.errors import AgentInputError, InvalidAgentOutputError
from app.agent.llm_client import LLMClient
from app.agent.prompt_loader import load_prompt
from app.core.schemas import CustomerIntent

INTENT_OUTPUT_CONTRACT: Final = (
    "Output contract for this call. It overrides any earlier instruction about tools or "
    "output schema.\n"
    "No tools are available: do not call or mention any tool.\n"
    'Return exactly one JSON object with these four keys and no others: "available_now", '
    '"preferred_installments", "requested_discount_pct", "desired_date".\n'
    "Use null for every value the customer did not state explicitly.\n"
    '"available_now" is a string with two decimals, for example "300.00". '
    '"preferred_installments" is an integer. '
    '"requested_discount_pct" is a string without a percent sign, for example "40". '
    '"desired_date" is a string in YYYY-MM-DD format, or null.\n'
    "Do not wrap the JSON in markdown and do not add commentary."
)


def extract_intent(
    message: str,
    client: LLMClient,
) -> CustomerIntent:
    """Extract intent from an already sanitized customer message."""

    if not isinstance(message, str):
        raise AgentInputError("Customer message must be a string")

    if not message.strip():
        raise AgentInputError("Customer message cannot be empty")

    system_prompt = f"{load_prompt('system_agent.txt')}\n\n{INTENT_OUTPUT_CONTRACT}"

    response = client.complete(
        system=system_prompt,
        user=message,
        schema=CustomerIntent,
    )

    if not isinstance(response, CustomerIntent):
        raise InvalidAgentOutputError("LLM client returned an invalid response type")

    return response
