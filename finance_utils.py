import re
from calendar import monthrange
from datetime import UTC, date, datetime
from math import isfinite

import numpy as np
import numpy_financial as npf


def build_mthly_schedule(principal, rate_per_period, n_periods) -> dict:
    """
    Build a payment schedule for a loan.

    Parameters:
    principal (float): The initial amount of the loan.
    rate_per_period (float): The interest rate per payment period (as a decimal).
    n_periods (int): The total number of payment periods.

    Returns:
    dict: Payment, interest, principal paid and outstanding balance for each period.
    """

    payment = -npf.pmt(rate_per_period, n_periods, principal)
    periods = np.arange(1, n_periods + 1)
    interests = -npf.ipmt(rate_per_period, periods, n_periods, principal)
    principal_paid = -npf.ppmt(rate_per_period, periods, n_periods, principal)

    balances = np.concatenate(([principal], principal - np.cumsum(principal_paid)))

    schedule = {
        0: {"payment": 0.0, "interest": 0.0, "principal_paid": 0.0, "balance": float(principal)}
    }

    for k in range(n_periods):
        schedule[k + 1] = {
            "payment": round(float(payment), 2),
            "interest": round(float(interests[k]), 2),
            "principal_paid": round(float(principal_paid[k]), 2),
            "balance": round(float(balances[k + 1]), 2),
        }

    return schedule


def monthly_due_dates(pivot_date: str, n: int) -> list[str]:
    """
    Return the ISO pivot date (period 0) and n monthly payment dates.
    Example: pivot_date="2024-01-31", n=3 returns
    ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"].
    """

    pivot = date.fromisoformat(pivot_date)
    end_of_month = pivot.day == monthrange(pivot.year, pivot.month)[1]
    dates = []

    for k in range(n + 1):
        year, month = divmod(pivot.year * 12 + pivot.month - 1 + k, 12)
        month += 1
        last_day = monthrange(year, month)[1]
        day = last_day if end_of_month else min(pivot.day, last_day)
        dates.append(date(year, month, day).isoformat())

    return dates


def validate_variables(
    principal=None, annual_rate=None, n=None, pivot_date=None, cash_flows=None
) -> bool:
    """Validate supplied variables; print errors and return False on failure."""
    try:
        if principal is not None:
            principal = float(principal)
            if not isfinite(principal) or principal <= 0:
                raise ValueError("principal must be a positive finite number")

        if annual_rate is not None:
            if isinstance(annual_rate, bool):
                raise ValueError("annual_rate must be between 0 and 3 (exclusive)")
            annual_rate = float(annual_rate)
            if not isfinite(annual_rate) or not 0 <= annual_rate < 3:
                raise ValueError("annual_rate must be between 0 and 3 (exclusive)")

        if n is not None and (type(n) is not int or not 1 <= n < 61):
            raise ValueError("n must be an integer between 1 and 60")

        if pivot_date is not None:
            if type(pivot_date) in (int, float):
                datetime.fromtimestamp(pivot_date, UTC).date()
            elif isinstance(pivot_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", pivot_date):
                date.fromisoformat(pivot_date)
            else:
                raise ValueError("pivot_date must be YYYY-MM-DD or Unix seconds")

        if cash_flows is not None:
            if not isinstance(cash_flows, list) or len(cash_flows) < 2:
                raise ValueError("cash_flows must be a list with at least two elements")
            if not all(isinstance(flow, (int, float)) for flow in cash_flows):
                raise ValueError("cash_flows must contain only numeric values")
            if cash_flows[0] >= 0:
                raise ValueError("The first cash flow must be negative (initial investment)")
            if np.sum(cash_flows[1:]) < -cash_flows[0]:
                raise ValueError("The net subsequent cash flows must cover the initial principal")

    except (ValueError, TypeError, OverflowError, OSError) as error:
        print(f"Validation error: {error}")
        return False

    return True


def build_dated_schedule(principal, annual_rate, n: int, pivot_date) -> dict:
    """
    Calculate fixed monthly payments when the annual nominal rate is known.

    Args:
        principal: Initial balance in currency units; supply a positive finite amount.
        annual_rate: Nominal annual rate as a decimal, not a percentage number:
            0.12 means 12%. Must be finite, non-negative and strictly below 3.
            This is NOT an effective annual rate; monthly rate = annual_rate / 12.
        n: Number of payments, an integer from 1 through 60 (integer type).
        pivot_date: Initial valuation date as YYYY-MM-DD or Unix seconds in UTC.
            First payment is one contractual month AFTER this date.

    Returns:
        A dictionary keyed by periods 0..n, with payment, interest, principal_paid,
        balance and ISO due_date per period. Period 0 is the initial balance,
        with no payment. Amounts are rounded independently to two decimals.
        Month-end pivots remain month end; other days preserve their original
        anchor and are clipped only in months where that day does not exist.

    Validation:
        Returns {} on validation failure; the validator prints the error.

    Notes:
        Contractual months, not actual-day accrual. No PayPal calls or charges.
        Use evaluate_cash_flows when the proposed payments are known but the rate is not.

    Example:
        build_dated_schedule(900, 0.12, 12, "2028-01-31")
    """

    # Dividing by 12 treats the input as a NOMINAL annual rate.
    # An EFFECTIVE annual rate would require (1 + annual_rate) ** (1 / 12) - 1.

    valid = validate_variables(
        principal=principal, annual_rate=annual_rate, n=n, pivot_date=pivot_date
    )

    if not valid:
        return {}
    else:
        monthly_rate = annual_rate / 12
        schedule = build_mthly_schedule(principal, monthly_rate, n)
        due_dates = monthly_due_dates(pivot_date, n)

        for period, due_date in enumerate(due_dates):
            schedule[period]["due_date"] = due_date

        return schedule


def evaluate_cash_flows(cash_flows: list[float]) -> dict:
    """Return the monthly internal rate of return using numpy_financial.irr.

    Args:
        cash_flows: Amounts in chronological order, starting with the negative
            initial balance, followed by monthly payments (which may differ).
            Each position is one contractual month; use 0 for an unpaid month.
            Use the same currency throughout. No dates are required.

    Returns:
        Dictionary with monthly_rate, effective_annual_rate and
        annual_nominal_rate, rounded to five decimals. Rates are decimal
        fractions: 0.01 means 1%. Returns {} on validation failure;
        the validator prints the error. Subsequent flows may be negative,
        but their net sum must cover the initial principal.
        Multiple sign changes can produce multiple IRRs.

    Example:
        evaluate_cash_flows([-10000] + [1000] * 11 + [950])
    """
    valid = validate_variables(cash_flows=cash_flows)
    if not valid:
        return {}
    else:
        rate = npf.irr(cash_flows)
        return {
            "monthly_rate": float(np.round(rate, 5)),
            "effective_annual_rate": float(np.round((1 + rate) ** 12 - 1, 5)),
            "annual_nominal_rate": float(np.round(rate * 12, 5)),
        }
