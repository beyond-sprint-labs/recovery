"""Deterministic text client for Recovery F1-06 demos."""

import json
from collections.abc import Mapping

from app.agent.prompt_loader import load_prompt


def _render_options(payload: Mapping[str, object]) -> list[str]:
    """Render only the approved alternatives supplied by the agent."""
    alternatives = payload.get("alternatives")

    if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= 2:
        raise ValueError("Expected one or two financial alternatives")

    lines: list[str] = []

    for index, item in enumerate(alternatives):
        if not isinstance(item, dict):
            raise ValueError("Invalid financial alternative")

        label = chr(ord("A") + index)

        if item.get("type") == "settlement_discount":
            lines.append(
                f"Option {label}: Pay ${item['amount_due_now']} today "
                f"with a {item['discount_pct']}% discount."
            )

        elif item.get("type") == "down_payment_installments":
            lines.append(
                f"Option {label}: Pay ${item['amount_due_now']} today, "
                f"followed by {item['installments']} monthly installments "
                f"of ${item['installment_amount']}. "
                f"Final installment: ${item['final_installment_amount']}. "
                f"Total paid: ${item['total_paid']}."
            )

        else:
            raise ValueError("Unsupported financial alternative type")

    return lines


class MockTextLLMClient:
    """Generate deterministic drafts without external API calls."""

    def generate_text(self, system: str, user: str) -> str:
        """Render figures from the backend-approved financial context."""

        explain_prompt = load_prompt("explain_alternatives.txt")
        customer_prompt = load_prompt("customer_message.txt")

        if system.strip() not in {explain_prompt, customer_prompt}:
            raise ValueError("Unsupported text generation prompt")

        payload = json.loads(user)
        lines = _render_options(payload)
        options_text = "\n".join(lines)

        if system.strip() == explain_prompt:
            return options_text

        return (
            "Hello,\n\n"
            "We would like to offer you the following payment options:\n\n"
            f"{options_text}\n\n"
            "Please let us know which option works best for you."
        )
