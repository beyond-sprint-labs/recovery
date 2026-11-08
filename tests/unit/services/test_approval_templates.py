"""Approval templates and their text-guard allow-list (F1-13, slice 2)."""

from decimal import Decimal

import pytest

from app.core.schemas import Alternative, AlternativeType
from app.finance import calculate_alternatives
from app.services.approval_templates import (
    build_final_message_allowed_numbers,
    render_customer_message,
)
from app.services.text_guard import check_text_numbers

POLICY = {
    "max_discount_pct": "15",
    "min_down_payment_pct": "20",
    "max_installments": 6,
    "max_financing_rate_pct": "2.0",
    "merchant_discount_rate_pct": "1.0",
}


@pytest.fixture(scope="module")
def alternatives() -> dict[AlternativeType, Alternative]:
    result = calculate_alternatives(
        {
            "engine_version": "1.0.0",
            "invoice": {
                "id": "INV-001",
                "currency": "USD",
                "balance": "1000.00",
                "due_date": "2026-10-15",
                "as_of_date": "2026-11-11",
            },
            "alternatives": [
                {"type": "settlement_discount", "discount_pct": "10"},
                {
                    "type": "down_payment_installments",
                    "down_payment_pct": "30",
                    "installments": 3,
                    "periodic_rate_pct": "1.5",
                },
            ],
            "policy": POLICY,
        }
    )
    parsed = [Alternative.model_validate(item) for item in result["alternatives"]]  # type: ignore[attr-defined]
    return {alt.type: alt for alt in parsed}


def test_settlement_message_matches_the_official_template(
    alternatives: dict[AlternativeType, Alternative],
) -> None:
    message = render_customer_message(
        invoice_id="INV-001", alternative=alternatives[AlternativeType.SETTLEMENT_DISCOUNT]
    )
    assert message == (
        "Hello, your proposed settlement terms for invoice INV-001 have been approved. "
        "You can settle the full balance today with a single payment of $900.00 "
        "(10% discount). Please review the terms and confirm below."
    )


def test_installments_message_matches_the_official_template(
    alternatives: dict[AlternativeType, Alternative],
) -> None:
    message = render_customer_message(
        invoice_id="INV-001",
        alternative=alternatives[AlternativeType.DOWN_PAYMENT_INSTALLMENTS],
    )
    assert message == (
        "Hello, your proposed installment arrangement for invoice INV-001 has been approved: "
        "pay $300.00 today, followed by 3 monthly payments of $240.37, for a total of "
        "$1021.10. Please review the schedule and confirm below."
    )


@pytest.mark.parametrize("alternative_type", list(AlternativeType))
def test_rendered_messages_pass_the_text_guard(
    alternatives: dict[AlternativeType, Alternative], alternative_type: AlternativeType
) -> None:
    alternative = alternatives[alternative_type]
    message = render_customer_message(invoice_id="INV-001", alternative=alternative)
    check = check_text_numbers(
        [message],
        build_final_message_allowed_numbers(alternative=alternative, invoice_id="INV-001"),
    )
    assert check.status == "PASSED", check.unmatched


def test_a_tampered_figure_is_caught_by_the_allow_list(
    alternatives: dict[AlternativeType, Alternative],
) -> None:
    alternative = alternatives[AlternativeType.SETTLEMENT_DISCOUNT]
    message = render_customer_message(invoice_id="INV-001", alternative=alternative)
    check = check_text_numbers(
        [message.replace("900.00", "850.00")],
        build_final_message_allowed_numbers(alternative=alternative, invoice_id="INV-001"),
    )
    assert check.status == "FAILED"
    assert "850.00" in check.unmatched


def test_allow_list_contains_only_the_figures_the_template_prints(
    alternatives: dict[AlternativeType, Alternative],
) -> None:
    allowed = build_final_message_allowed_numbers(
        alternative=alternatives[AlternativeType.DOWN_PAYMENT_INSTALLMENTS],
        invoice_id="INV-001",
    )
    assert {
        Decimal("300.00"),
        Decimal("240.37"),
        Decimal("1021.10"),
        Decimal("3"),
    } <= allowed.values
    assert Decimal("1006.91") not in allowed.values  # present value is merchant-only
    assert Decimal("240.36") not in allowed.values
    assert Decimal("6.91") not in allowed.values
