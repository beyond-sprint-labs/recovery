"""F1-05: contract entry point calculate_alternatives(EngineRequest) -> EngineResult."""

import pytest

from app.finance import FinanceValidationError, calculate_alternatives


def _request(alternatives):
    return {
        "engine_version": "1.0.0",
        "invoice": {
            "id": "INV-001",
            "currency": "USD",
            "balance": "1000.00",
            "due_date": "2026-10-15",
            "as_of_date": "2026-11-01",
        },
        "alternatives": alternatives,
        "policy": {
            "max_discount_pct": "15",
            "min_down_payment_pct": "20",
            "max_installments": 6,
            "max_financing_rate_pct": "2.0",
            "merchant_discount_rate_pct": "1.0",
        },
    }


def test_contract_example_returns_both_alternatives_in_order():
    result = calculate_alternatives(
        _request(
            [
                {"type": "settlement_discount", "discount_pct": "10"},
                {
                    "type": "down_payment_installments",
                    "down_payment_pct": "30",
                    "installments": 3,
                    "periodic_rate_pct": "1.5",
                },
            ]
        )
    )
    assert result["engine_version"] == "1.0.0"
    settlement, installments = result["alternatives"]
    assert settlement["type"] == "settlement_discount"
    assert settlement["amount_due_now"] == "900.00"
    assert installments["installment_amount"] == "240.37"
    assert installments["total_paid"] == "1021.10"
    assert installments["present_value"] == "1006.91"
    assert installments["merchant_difference_vs_balance"] == "6.91"
    assert [row["n"] for row in installments["schedule"]] == [0, 1, 2, 3]
    assert installments["schedule"][0]["due_date"] == "2026-11-01"


def test_discount_over_policy_is_reported_not_raised():
    result = calculate_alternatives(
        _request([{"type": "settlement_discount", "discount_pct": "40"}])
    )
    (alternative,) = result["alternatives"]
    assert alternative["policy_ok"] is False
    assert alternative["violations"] == [
        {"code": "MAX_DISCOUNT_PCT", "limit": "15", "attempted": "40", "unit": "pct"}
    ]


def test_unknown_request_key_is_rejected():
    request = _request([{"type": "settlement_discount", "discount_pct": "10"}])
    request["policy_override"] = {"max_discount_pct": "100"}
    with pytest.raises(FinanceValidationError):
        calculate_alternatives(request)


def test_unknown_alternative_type_and_extra_term_are_rejected():
    with pytest.raises(FinanceValidationError):
        calculate_alternatives(_request([{"type": "refinance", "discount_pct": "10"}]))
    with pytest.raises(FinanceValidationError):
        calculate_alternatives(
            _request([{"type": "settlement_discount", "discount_pct": "10", "extra": "1"}])
        )
