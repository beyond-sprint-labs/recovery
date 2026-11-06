"""Deterministic text client for Recovery F1-06 demos."""

import json


class MockTextLLMClient:
    """Generate predefined financial drafts without external API calls."""

    def generate_text(self, system: str, user: str) -> str:
        """Render a deterministic draft using engine-provided figures."""

        payload = json.loads(user)
        alternatives = payload.get("alternatives")

        if not isinstance(alternatives, list) or len(alternatives) != 2:
            raise ValueError("Expected two financial alternatives")

        by_type = {item["type"]: item for item in alternatives}

        settlement = by_type["settlement_discount"]
        installments = by_type["down_payment_installments"]

        def figure(item: dict, field: str) -> str:
            value = item.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (str, int))
                or not str(value).strip()
            ):
                raise ValueError(f"Invalid financial figure: {field}")
            return str(value)

        settlement_amount = figure(settlement, "amount_due_now")
        discount = figure(settlement, "discount_pct")

        down_payment = figure(installments, "amount_due_now")
        installment_count = figure(installments, "installments")
        installment_amount = figure(installments, "installment_amount")
        final_amount = figure(installments, "final_installment_amount")
        total_paid = figure(installments, "total_paid")

        option_a = f"Option A: Pay ${settlement_amount} today with a {discount}% discount."

        option_b = (
            f"Option B: Pay ${down_payment} today, followed by "
            f"{installment_count} monthly installments of "
            f"${installment_amount}. "
            f"Final installment: ${final_amount}. "
            f"Total paid: ${total_paid}."
        )

        if "You are explaining two approved" in system:
            return f"{option_a}\n{option_b}"

        if "Draft a cordial, professional message" in system:
            return (
                "Hello,\n\n"
                "We would like to offer you the following "
                "payment options:\n\n"
                f"{option_a}\n{option_b}\n\n"
                "Please let us know which option works best for you."
            )

        raise ValueError("Unsupported text generation prompt")
