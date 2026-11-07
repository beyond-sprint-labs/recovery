"""Recovery F1-06 agent orchestration."""

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import ValidationError

from app.agent.errors import AgentInputError, InvalidAgentOutputError
from app.agent.intent_extractor import extract_intent
from app.agent.llm_client import LLMClient, TextLLMClient
from app.agent.schemas import AgentOutput
from app.core.schemas import Alternative, CustomerIntent, SettlementTerms

# The backend owns invoice balance, dates, policy, and calculations.
ToolRunner = Callable[[CustomerIntent], object]

# Temporary contract until the backend publishes an EngineResult type.
EngineResult = Mapping[str, object]

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def _figures(alt: Alternative) -> dict[str, object]:
    """Allow-list financial figures without exposing internal engine data."""
    if isinstance(alt.terms, SettlementTerms):
        return {
            "type": alt.type.value,
            "amount_due_now": alt.amount_due_now,
            "total_paid": alt.total_paid,
            "discount_pct": alt.terms.discount_pct,
        }

    if alt.installment_amount is None or not alt.schedule:
        raise AgentInputError("Installment alternative missing required figures")

    return {
        "type": alt.type.value,
        "amount_due_now": alt.amount_due_now,
        "installments": alt.terms.installments,
        "installment_amount": alt.installment_amount,
        "final_installment_amount": alt.schedule[-1].amount,
        "total_paid": alt.total_paid,
    }


def _prepare_financial_context(engine_result: EngineResult) -> str:
    """Validate and serialize one or two approved alternatives."""

    raw = engine_result.get("alternatives")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 2:
        raise AgentInputError("EngineResult must contain one or two alternatives")

    approved: list[dict[str, object]] = []
    seen: set[str] = set()

    for item in raw:
        try:
            alt = Alternative.model_validate(item)
        except ValidationError as error:
            raise AgentInputError("Alternative does not match the engine contract") from error

        if not alt.policy_ok or alt.violations:
            raise AgentInputError("Cannot draft blocked alternatives")

        if alt.type.value in seen:
            raise AgentInputError("Duplicate alternative type")

        seen.add(alt.type.value)
        approved.append(_figures(alt))

    return json.dumps(
        {"alternatives": approved},
        ensure_ascii=False,
        sort_keys=True,
    )


class NegotiationAgent:
    """Extract intent and generate financial text drafts."""

    def __init__(
        self,
        client: LLMClient,
        text_client: TextLLMClient | None = None,
    ):
        self.client = client
        self.text_client = text_client

    def run(
        self,
        sanitized_message: str,
        tool_runner: ToolRunner,
    ) -> AgentOutput:
        """Process a server-sanitized customer message."""

        intent = extract_intent(sanitized_message, self.client)

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

        # Financial context and policy are owned by the backend.
        tool_runner(intent)

        return AgentOutput(intent=intent)

    def _generate_financial_text(
        self,
        engine_result: EngineResult,
        prompt_filename: str,
    ) -> str:
        """Generate untrusted text using approved financial figures."""

        if self.text_client is None:
            raise AgentInputError("Text LLM client is not configured")

        financial_context = _prepare_financial_context(engine_result)

        system_prompt = (PROMPT_DIR / prompt_filename).read_text(encoding="utf-8")

        result = self.text_client.generate_text(
            system=system_prompt,
            user=financial_context,
        )

        if not isinstance(result, str) or not result.strip():
            raise InvalidAgentOutputError("Text LLM returned an empty response")

        # RecoveryService must validate this text with text_guard.
        return result

    def explain_alternatives(
        self,
        engine_result: EngineResult,
    ) -> str:
        """Generate a merchant-facing explanation."""
        return self._generate_financial_text(
            engine_result,
            "explain_alternatives.txt",
        )

    def draft_customer_message(
        self,
        engine_result: EngineResult,
    ) -> str:
        """Generate a customer-facing message draft."""
        return self._generate_financial_text(
            engine_result,
            "customer_message.txt",
        )
