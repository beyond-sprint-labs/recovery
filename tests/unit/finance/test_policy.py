"""F1-05: policy-first validation and totality of the financial engine."""

from decimal import Decimal

import pytest

from app.finance.engine import build_alternative
from app.finance.policy import validate

POLICY = {
    "currency": "USD",
    "max_discount_pct": "15",
    "min_down_payment_pct": "20",
    "max_installments": 6,
    "max_financing_rate_pct": "2.0",
    "merchant_discount_rate_pct": "1.0",
}


def test_discount_over_limit_is_reported_without_schedule_math():
    assert validate({"discount_pct": "40"}, POLICY) == [
        {"code": "MAX_DISCOUNT_PCT", "limit": "15", "attempted": "40", "unit": "pct"}
    ]


def test_discount_at_limit_is_allowed():
    assert validate({"discount_pct": "15"}, POLICY) == []


def test_installment_violations_keep_contract_order_and_units():
    violations = validate(
        {"down_payment_pct": "10", "installments": 60, "periodic_rate_pct": "5"}, POLICY
    )
    assert [v["code"] for v in violations] == [
        "MIN_DOWN_PAYMENT_PCT",
        "MAX_INSTALLMENTS",
        "MAX_FINANCING_RATE_PCT",
    ]
    assert violations[1] == {
        "code": "MAX_INSTALLMENTS",
        "limit": "6",
        "attempted": "60",
        "unit": "count",
    }


@pytest.mark.parametrize("balance", ["0.00", "1.00", "4.54", "50.00", "1000.00", "5000.00"])
@pytest.mark.parametrize("installments", [1, 3, 6, 7, 24, 60, 120])
@pytest.mark.parametrize("rate", ["0", "1.5", "2", "10"])
def test_valid_terms_never_raise_and_are_flagged_by_policy(balance, installments, rate):
    alternative = build_alternative(
        balance=balance,
        alternative_type="down_payment_installments",
        terms={"down_payment_pct": "30", "installments": installments, "periodic_rate_pct": rate},
        policy=POLICY,
        pivot_date="2026-11-11",
    )
    within_policy = installments <= 6 and Decimal(rate) <= Decimal("2.0")
    assert alternative["policy_ok"] is within_policy
    assert sum(Decimal(row["principal"]) for row in alternative["schedule"]) == Decimal(balance)
