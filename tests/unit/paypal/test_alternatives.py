"""Tests for mapping approved alternatives to PayPal invoices (F1-18b)."""

import pytest

from app.core.schemas import Alternative, AlternativeType, SettlementTerms
from app.paypal.alternatives import (
    AlternativeMappingError,
    build_replacement_request,
    confirmation_label,
    replacement_invoice_number,
    select_approved_alternative,
    simulation_notice,
)


@pytest.fixture
def settlement_alt() -> Alternative:
    return Alternative(
        type=AlternativeType.SETTLEMENT_DISCOUNT,
        terms=SettlementTerms(discount_pct="10"),
        amount_due_now="900.00",
        installment_amount=None,
        total_paid="900.00",
        present_value="900.00",
        financing_cost="0.00",
        merchant_difference_vs_balance="-100.00",
        policy_ok=True,
        violations=[],
        schedule=[
            {
                "n": 0,
                "due_date": "2026-11-11",
                "amount": "900.00",
                "principal": "900.00",
                "interest": "0.00",
            }
        ],
    )


def test_replacement_invoice_number_is_deterministic():
    # The number must be deterministic to prevent duplicate creation on retries.
    prop_id = "prop_abc123"
    assert replacement_invoice_number(prop_id) == "REC-prop_abc123"
    assert replacement_invoice_number(prop_id) == "REC-prop_abc123"


def test_build_replacement_request(settlement_alt):
    req = build_replacement_request(
        proposal_id="prop_123", alternative=settlement_alt, recipient_email="test@example.com"
    )
    assert req.invoice_number == "REC-prop_123"
    assert req.amount == "900.00"
    assert req.recipient_email == "test@example.com"


def test_select_approved_alternative_fails_if_blocked(settlement_alt):
    blocked_alt = settlement_alt.model_copy(update={"policy_ok": False})
    
    with pytest.raises(
        AlternativeMappingError, match="The approved alternative violates the policy"
    ):
        select_approved_alternative([blocked_alt], AlternativeType.SETTLEMENT_DISCOUNT)


def test_labels_and_notices(settlement_alt):
    assert confirmation_label(AlternativeType.SETTLEMENT_DISCOUNT) == "Payment confirmed"
    assert simulation_notice(AlternativeType.SETTLEMENT_DISCOUNT) is None
