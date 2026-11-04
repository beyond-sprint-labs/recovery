"""Monthly dates and JSON-compatible payment schedules.

Public interface: build_dated_schedule(principal, periodic_rate_pct, n, pivot_date).
Principal is already financed, after the down payment. Rates are monthly
percentages; payments are due at the end of each period. Down payment rows and
complete Alternative construction remain outside this helper.
"""

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext
from typing import TypedDict

from app.finance.engine import (
    WORKING_PRECISION,
    FinanceCalculationError,
    FinanceValidationError,
    PaymentAmounts,
    _validate_installments,
    _validate_money,
    _validate_pct,
    build_mthly_schedule,
    format_money,
    money_to_decimal,
)


class ScheduleItem(TypedDict):
    """Plain JSON-compatible output; no third-party model required."""

    n: int
    due_date: str
    amount: str
    principal: str
    interest: str


def _parse_date(value: object) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise FinanceValidationError("invalid calendar date") from error
    raise FinanceValidationError("pivot_date must be a date or exact YYYY-MM-DD")


@dataclass(frozen=True)
class ScheduleInput:
    """Validated local input for principal AFTER any down payment.

    Zero principal is allowed by Money. Policy evaluation and Alternative
    assembly live in engine.build_alternative. '2' means 2% per period.
    """

    principal: str
    periodic_rate_pct: str
    installments: int
    pivot_date: date | str
    currency: str = "USD"

    def __post_init__(self) -> None:
        _validate_money(self.principal)
        _validate_pct(self.periodic_rate_pct)
        _validate_installments(self.installments)
        if not isinstance(self.currency, str) or self.currency != "USD":
            raise FinanceValidationError("currency must be USD")
        object.__setattr__(self, "pivot_date", _parse_date(self.pivot_date))


def validate_variables(
    *, principal: str, periodic_rate_pct: str, n: int, pivot_date: date | str
) -> ScheduleInput:
    """Return validated data or raise; replaces the legacy boolean interface."""
    return ScheduleInput(
        principal=principal,
        periodic_rate_pct=periodic_rate_pct,
        installments=n,
        pivot_date=pivot_date,
    )


def monthly_due_dates(pivot_date: date | str, n: int) -> list[date]:
    """Return pivot plus n dates; preserve original day or end-of-month anchor.

    Returns date objects, unlike the old string output. Pivot is a date anchor,
    not automatically a scheduled payment or a down payment.
    """
    pivot = _parse_date(pivot_date)
    count = _validate_installments(n)
    end_of_month = pivot.day == monthrange(pivot.year, pivot.month)[1]
    dates = []
    try:
        for k in range(count + 1):
            year, month = divmod(pivot.year * 12 + pivot.month - 1 + k, 12)
            month += 1
            last_day = monthrange(year, month)[1]
            day = last_day if end_of_month else min(pivot.day, last_day)
            dates.append(date(year, month, day))
    except ValueError as error:
        raise FinanceValidationError("schedule exceeds the supported calendar") from error
    return dates


def _serialize_payment(row: PaymentAmounts, n: int, due_date: date) -> ScheduleItem:
    if not isinstance(row, PaymentAmounts):
        raise FinanceCalculationError("math hook must return PaymentAmounts rows")
    for name in ("amount", "principal", "interest"):
        value = getattr(row, name)
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise FinanceCalculationError(f"payment {n}: {name} must be nonnegative Decimal")
        # Serialization also checks range. Do not silently fix unreconciled rows.
        serialized = format_money(value)
        if value != Decimal(serialized):
            raise FinanceCalculationError(f"payment {n}: {name} must already be in cents")
    if row.amount != row.principal + row.interest:
        raise FinanceCalculationError(f"payment {n}: amount must equal principal plus interest")
    return ScheduleItem(
        n=n,
        due_date=due_date.isoformat(),
        amount=format_money(row.amount),
        principal=format_money(row.principal),
        interest=format_money(row.interest),
    )


def build_dated_schedule(
    principal: str, periodic_rate_pct: str, n: int, pivot_date: date | str
) -> list[ScheduleItem]:
    """External validation boundary; raises FinanceError subclasses on failure.

    Payments 1..n, first one month AFTER pivot; no down payment row here.
    engine.build_alternative adds the immediate payment at n=0.
    Input rate precision is preserved; only monetary amounts are rounded.
    Results are JSON-compatible dictionaries with ISO dates and money strings.
    """
    request = validate_variables(
        principal=principal,
        periodic_rate_pct=periodic_rate_pct,
        n=n,
        pivot_date=pivot_date,
    )
    dates = monthly_due_dates(request.pivot_date, request.installments)
    financed = money_to_decimal(request.principal)
    try:
        with localcontext() as context:
            context.prec = WORKING_PRECISION
            context.rounding = ROUND_HALF_UP
            rate = Decimal(request.periodic_rate_pct) / Decimal("100")
            rows = build_mthly_schedule(financed, rate, request.installments)
            if not isinstance(rows, list) or len(rows) != request.installments:
                raise FinanceCalculationError("math hook must return one row per installment")
            result = [
                _serialize_payment(row, index, dates[index])
                for index, row in enumerate(rows, start=1)
            ]
            if sum((row.principal for row in rows), Decimal("0")) != financed:
                raise FinanceCalculationError("scheduled principal must equal financed principal")
            return result
    except DecimalException as error:
        raise FinanceCalculationError("Decimal calculation failed") from error
