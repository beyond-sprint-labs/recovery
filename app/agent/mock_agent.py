from app.core.schemas import CustomerIntent


def mock_agent_run(message: str, scenario_id: str | None = None) -> CustomerIntent:
    """
    # Simulates the LLM agent responses based on the message
    # or a predefined scenario_id (S01...S12).
    """

    # 1. Evaluate by scenario_id (Ideal for deterministic testing)
    if scenario_id == "S03_exceeds_discount":
        return CustomerIntent(requested_discount_pct="40")

    if scenario_id == "S01_pay_partial":
        return CustomerIntent(available_now="300.00", preferred_installments=3)

    # 2. Evaluate by natural language (Fallback)
    message_lower = message.lower()

    if "40%" in message or "40 %" in message:
        return CustomerIntent(requested_discount_pct="40")

    if "300" in message_lower and ("pay" in message_lower or "pagar" in message_lower):
        return CustomerIntent(available_now="300.00", preferred_installments=3)

    if "10%" in message or "descuento" in message_lower:
        return CustomerIntent(requested_discount_pct="10")

    # If it understands nothing, it returns an empty intent.
    return CustomerIntent()
