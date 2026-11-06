"""Recovery F1-06 agent orchestration."""

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.agent.intent_extractor import extract_intent
from app.agent.llm_client import LLMClient, TextLLMClient
from app.core.schemas import CustomerIntent

# The backend owns invoice balance, dates, policy, and calculations.
ToolRunner = Callable[[CustomerIntent], object]

# Temporary contract until the backend publishes an EngineResult type.
EngineResult = Mapping[str, object]

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


class AgentOutput(BaseModel):
    """Structured agent output agreed with the backend."""

    model_config = ConfigDict(extra="forbid")

    intent: CustomerIntent
    explanation: str | None = None
    customer_message_draft: str | None = None


def _prepare_financial_context(
    engine_result: EngineResult,
) -> str:
    """Serialize allowlisted figures from approved alternatives."""

    alternatives = engine_result.get("alternatives")

    if not isinstance(alternatives, list):
        raise ValueError("EngineResult must contain alternatives")

    if len(alternatives) != 2:
        raise ValueError("Exactly two alternatives are required")

    expected_types = {
        "settlement_discount",
        "down_payment_installments",
    }

    approved = []

    for alternative in alternatives:
        if not isinstance(alternative, Mapping):
            raise ValueError("Invalid alternative")

        if alternative.get("policy_ok") is not True:
            raise ValueError("Cannot draft blocked alternatives")

        kind = alternative.get("type")

        if kind not in expected_types:
            raise ValueError("Unexpected alternative type")

        terms = alternative.get("terms")
        schedule = alternative.get("schedule")

        if not isinstance(terms, Mapping):
            raise ValueError("Invalid alternative terms")

        if not isinstance(schedule, list) or not schedule:
            raise ValueError("Invalid payment schedule")

        if not all(isinstance(row, Mapping) for row in schedule):
            raise ValueError("Invalid payment schedule entries")

        figures = {
            "type": kind,
            "amount_due_now": alternative.get("amount_due_now"),
            "installment_amount": alternative.get("installment_amount"),
            "total_paid": alternative.get("total_paid"),
        }

        if kind == "settlement_discount":
            figures["discount_pct"] = terms.get("discount_pct")
            required = (
                "amount_due_now",
                "total_paid",
                "discount_pct",
            )
        else:
            figures["installments"] = terms.get("installments")
            figures["final_installment_amount"] = schedule[-1].get("amount")
            required = (
                "amount_due_now",
                "installment_amount",
                "total_paid",
                "installments",
                "final_installment_amount",
            )

        if any(figures.get(field) is None for field in required):
            raise ValueError("Missing required financial figures")

        approved.append(figures)

    if {item["type"] for item in approved} != expected_types:
        raise ValueError("Both alternative types are required")

    return json.dumps(
        {"alternatives": approved},
        ensure_ascii=False,
        sort_keys=True,
    )


class RecoveryAgent:
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
            raise RuntimeError("Text LLM client is not configured")

        financial_context = _prepare_financial_context(engine_result)

        system_prompt = (PROMPT_DIR / prompt_filename).read_text(encoding="utf-8")

        result = self.text_client.generate_text(
            system=system_prompt,
            user=financial_context,
        )

        if not isinstance(result, str) or not result.strip():
            raise ValueError("Text LLM returned an empty response")

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
