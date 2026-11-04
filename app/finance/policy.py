"""Pure policy-limit validation for alternative terms (F1-05, consumed by F1-15).

No schedule math happens here, so the service can block out-of-policy terms
before any calculation. Percentages are compared as exact Decimals and are
never rounded. Malformed terms raise FinanceValidationError; limits that are
exceeded are returned as RuleHit-style dictionaries.
"""

from collections.abc import Mapping
from decimal import Decimal

from app.finance.engine import (
    FinanceValidationError,
    FinancialPolicy,
    _validate_installments,
    _validate_pct,
)

Violation = dict[str, str]

_SETTLEMENT_KEYS = frozenset({"discount_pct"})
_INSTALLMENT_KEYS = frozenset({"down_payment_pct", "installments", "periodic_rate_pct"})


def _violation(code: str, attempted: str, limit: str, unit: str = "pct") -> Violation:
    return {"code": code, "limit": limit, "attempted": attempted, "unit": unit}


def _as_policy(policy: FinancialPolicy | Mapping[str, object]) -> FinancialPolicy:
    if isinstance(policy, FinancialPolicy):
        return policy
    if isinstance(policy, Mapping):
        try:
            return FinancialPolicy(**policy)
        except TypeError as error:
            raise FinanceValidationError("policy fields must match the Policy contract") from error
    raise FinanceValidationError("policy must be FinancialPolicy or a Policy dictionary")


def validate(
    terms: Mapping[str, object], policy: FinancialPolicy | Mapping[str, object]
) -> list[Violation]:
    """Return the policy limits exceeded by the given terms (empty list if none)."""
    limits = _as_policy(policy)
    if not isinstance(terms, Mapping):
        raise FinanceValidationError("terms must be a dictionary")
    keys = frozenset(terms)
    violations: list[Violation] = []
    if keys == _SETTLEMENT_KEYS:
        discount = _validate_pct(terms["discount_pct"])
        if Decimal(discount) > Decimal(limits.max_discount_pct):
            violations.append(_violation("MAX_DISCOUNT_PCT", discount, limits.max_discount_pct))
    elif keys == _INSTALLMENT_KEYS:
        down_payment = _validate_pct(terms["down_payment_pct"])
        count = _validate_installments(terms["installments"])
        rate = _validate_pct(terms["periodic_rate_pct"])
        if Decimal(down_payment) < Decimal(limits.min_down_payment_pct):
            violations.append(
                _violation("MIN_DOWN_PAYMENT_PCT", down_payment, limits.min_down_payment_pct)
            )
        if count > limits.max_installments:
            violations.append(
                _violation("MAX_INSTALLMENTS", str(count), str(limits.max_installments), "count")
            )
        if Decimal(rate) > Decimal(limits.max_financing_rate_pct):
            violations.append(
                _violation("MAX_FINANCING_RATE_PCT", rate, limits.max_financing_rate_pct)
            )
    else:
        raise FinanceValidationError("terms must match SettlementTerms or InstallmentTerms")
    return violations
