"""Stub for F1-06 (Agent). Replaced when the ML agent is ready."""

from app.core.schemas import CustomerIntent


def run_agent(customer_message: str, scenario_id: str | None = None) -> CustomerIntent:
    # If the user asks for 40% off, we return 40 (triggers BLOCKED).
    if "40" in customer_message:
        return CustomerIntent(requested_discount_pct="40")
    # If the user says "300", we return a partial payment intent.
    if "300" in customer_message:
        return CustomerIntent(available_now="300.00", preferred_installments=3)
    # Default fallback
    return CustomerIntent()
