"""F1-05: contract validation and monthly amortization using standard Python.

A) Ready: validate inputs, convert strings to Decimal, generate dates, validate
   results and return dictionaries matching the ScheduleItem JSON fields.
B) Amortization and the equally spaced monthly rate solver are implemented.

Changes from the original module:
- No numpy, numpy_financial, Pydantic or third-party imports; standard library only.
- External money: strings such as '1000.00'; internal money: Decimal, never float.
- Input rate: percentage PER PERIOD ('2' = 2%), not an annual fractional rate.
- Installments: int from 1 to 120; booleans and strings are rejected.
- Dates: date or YYYY-MM-DD; timestamps are no longer accepted.
- Errors: exceptions instead of printing errors and returning False or {}.
- External schedule: a list of dictionaries with the ScheduleItem fields.

Input rates are not rounded; Pct limits input to four decimal places.
Solver uses six-decimal precision and returns four decimal places with ROUND_HALF_UP.
Periods are monthly, with payments at the end of each period. The merchant discount rate is
also per period and is independent of the financing rate.

Agreed rules: q(x) = quantize(Decimal('0.01'), rounding=ROUND_HALF_UP).
- Down payment: q(balance * down_pct / 100).
- Discount amount: q(balance * discount_pct / 100).
- Payment: q(PMT); PMT = P*r / (1-(1+r)**(-n)); if r=0, PMT=P/n.
- Interest per period: q(outstanding balance * r).
- Final payment: remaining balance + interest for that period.
- PV: discount each cash flow without rounding; apply q only once at the end.
- Difference: rounded PV minus original balance, serialized as SignedMoney.

Golden case: balance 1000.00; down payment 30%; n=3; financing rate 1.5%;
merchant discount rate 1.0%. Down payment 300.00; financed principal 700.00;
payments 240.37 / 240.37 / 240.36; total 1021.10; PV 1006.91; difference 6.91.

build_alternative builds either financial Alternative from explicit terms and
server-side policy. The schedule includes the immediate payment at n=0.
RecoveryService remains responsible for proposal states, audit and persistence.

Date generation and the public dated-schedule interface live in schedule.py.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext

ENGINE_VERSION = "1.0.0"
CENT = Decimal("0.01")
RATE_QUANTUM = Decimal("0.000001")
RATE_OUTPUT_QUANTUM = Decimal("0.0001")
WORKING_PRECISION = 40  # Proposed working precision; not a contract requirement.
# Mirrors F1-02 without importing Pydantic; keep aligned with the shared contract.
_MONEY_PATTERN = re.compile(r"(0|[1-9][0-9]{0,11})\.[0-9]{2}")
_SIGNED_MONEY_PATTERN = re.compile(r"-?(0|[1-9][0-9]{0,11})\.[0-9]{2}")
_PCT_PATTERN = re.compile(r"(0|[1-9][0-9]{0,2})(\.[0-9]{1,4})?")


class FinanceError(Exception):
    """Base module error. The caller decides HTTP/status mapping."""


class FinanceValidationError(FinanceError, ValueError):
    """Invalid input, distinct from policy violations and calculation failures."""


class FinanceCalculationError(FinanceError, ArithmeticError):
    """Calculation failed or produced an inconsistent result."""


def _validate_installments(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 120:
        raise FinanceValidationError("installments must be an integer in 1..120")
    return value


def _validate_money(value: object) -> str:
    if not isinstance(value, str) or _MONEY_PATTERN.fullmatch(value) is None:
        raise FinanceValidationError("amount must be a nonnegative Money string with 2 decimals")
    return value


def _validate_pct(value: object) -> str:
    if (
        not isinstance(value, str)
        or _PCT_PATTERN.fullmatch(value) is None
        or Decimal(value) > Decimal("100")
    ):
        raise FinanceValidationError("rate must be a percentage string in 0..100, up to 4 decimals")
    return value


def money_to_decimal(value: str) -> Decimal:
    return Decimal(_validate_money(value))


def financing_rate_within_policy(periodic_rate_pct: str, max_financing_rate_pct: str) -> bool:
    """Compare validated periodic percentages as Decimal, without rounding.

    False is a policy violation, not malformed input. Does not evaluate the other
    Policy limits. The merchant discount rate does not participate here.
    """
    rate = Decimal(_validate_pct(periodic_rate_pct))
    limit = Decimal(_validate_pct(max_financing_rate_pct))
    return rate <= limit


def format_money(value: Decimal, *, signed: bool = False) -> str:
    """Serialize HALF_UP cents. Signed output is only for differences.

    This boundary does not define intermediate amortization rounding rules.
    """
    if not isinstance(value, Decimal) or not value.is_finite():
        raise FinanceCalculationError("amount must be a finite Decimal")
    if not signed and value < 0:
        raise FinanceCalculationError("Money cannot be negative")
    try:
        with localcontext() as context:
            context.prec = WORKING_PRECISION
            rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)
        if rounded == 0:
            rounded = Decimal("0.00")
        result = format(rounded, ".2f")
        pattern = _SIGNED_MONEY_PATTERN if signed else _MONEY_PATTERN
        if pattern.fullmatch(result) is None:
            raise FinanceCalculationError("amount exceeds the money contract")
        return result
    except DecimalException as error:
        raise FinanceCalculationError("amount exceeds the money contract") from error


@dataclass(frozen=True)
class PaymentAmounts:
    """Internal math output: nonnegative, reconciled Decimal cents per payment."""

    amount: Decimal
    principal: Decimal
    interest: Decimal


def build_monthly_schedule(
    principal: Decimal, rate_per_period: Decimal, n_periods: int
) -> list[PaymentAmounts]:
    """End-of-period amortization: payment = LOAN / a_n,i, using Decimal only.

    The rate is a fraction PER PERIOD: Decimal('0.015') means 1.5%.
    Principal must be in cents. Returns exactly n_periods rows.
    If rounding a fixed payment overpays principal before the final period,
    reject the plan rather than produce a negative balance or payment.
    """
    _validate_installments(n_periods)
    if not isinstance(principal, Decimal) or not principal.is_finite() or principal < 0:
        raise FinanceValidationError("principal must be a finite nonnegative Decimal")
    if (
        not isinstance(rate_per_period, Decimal)
        or not rate_per_period.is_finite()
        or not Decimal("0") <= rate_per_period <= Decimal("1")
    ):
        raise FinanceValidationError("rate_per_period must be a Decimal fraction in 0..1")
    if principal != Decimal(format_money(principal)):
        raise FinanceValidationError("principal must already be in cents")

    try:
        with localcontext() as context:
            context.prec = WORKING_PRECISION
            context.rounding = ROUND_HALF_UP
            if rate_per_period == 0:
                annuity_factor = Decimal(n_periods)
            else:
                v = Decimal("1") / (Decimal("1") + rate_per_period)
                # a_n,i = v + v**2 + ... + v**n = (1-v**n)/i.
                # The equivalent sum avoids subtracting nearly equal numbers
                # when the rate is very small. The rate is not rounded.
                annuity_factor = sum((v**k for k in range(1, n_periods + 1)), Decimal("0"))
            payment = (principal / annuity_factor).quantize(CENT, rounding=ROUND_HALF_UP)
            balance = principal
            rows = []
            for period in range(1, n_periods + 1):
                interest = (balance * rate_per_period).quantize(CENT, rounding=ROUND_HALF_UP)
                due = balance + interest
                # Clamp the rounded fixed payment so the schedule is defined for every
                # valid input: never below the period interest, never above what is owed.
                amount = due if period == n_periods else min(max(payment, interest), due)
                principal_paid = amount - interest
                rows.append(PaymentAmounts(amount, principal_paid, interest))
                balance -= principal_paid
            return rows
    except DecimalException as error:
        raise FinanceCalculationError("Decimal amortization failed") from error


@dataclass(frozen=True)
class CashFlowRates:
    """Internal Decimal fractions, NOT a new JSON contract (0.02 means 2%).

    All fields have four decimal places. Annual rates may exceed Pct bounds;
    never put them into periodic fields.
    """

    monthly_rate: Decimal
    effective_annual_rate: Decimal
    annual_nominal_rate: Decimal


def evaluate_cash_flows(cash_flows: list[Decimal], *, max_iterations: int = 21) -> CashFlowRates:
    """Solve a monthly rate in [0%, 200%] by Decimal bisection.

    Flows are equally spaced: negative financed principal at t=0, followed by
    1..120 nonnegative monthly payments, including at least one positive payment.
    These conventional flows make the error strictly increasing and the root
    unique if bracketed. Later negative flows are rejected, not silently treated
    as a monotonic problem. Calendar dates do not participate in this calculation.

    Error = initial principal - sum(payment_t / (1 + rate)**t).
    Positive error: decrease the rate. Negative error: increase the rate.
    The solver resolves six decimal places and returns fractions rounded to four,
    not percentages. Annual rates use the six-decimal monthly estimate, not
    the four-decimal returned value. Input contractual rates are never rounded.
    This solver's 200% bound does not change Pct's 100% external input limit.

    Stop once the bracket is at most 1e-6 wide (at most 21 bisections).
    If it straddles a rounding boundary, evaluate that boundary once to choose
    the correct six-decimal monthly rate. No monetary residual tolerance is
    imposed: rounding the output rate can change the discounted monetary value.
    Invalid inputs raise FinanceValidationError. An out-of-range root, numerical
    failure or nonconvergence raises FinanceCalculationError for the caller to catch.
    """
    if not isinstance(cash_flows, list) or not 2 <= len(cash_flows) <= 121:
        raise FinanceValidationError("cash_flows must contain an initial flow and 1..120 payments")
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in cash_flows):
        raise FinanceValidationError("cash_flows must contain only finite Decimal values")
    if cash_flows[0] >= 0:
        raise FinanceValidationError("initial cash flow must be negative")
    if any(value < 0 for value in cash_flows[1:]):
        raise FinanceValidationError("subsequent cash flows must be nonnegative for bisection")
    if not any(value > 0 for value in cash_flows[1:]):
        raise FinanceValidationError("at least one subsequent cash flow must be positive")
    if type(max_iterations) is not int or max_iterations < 1:
        raise FinanceValidationError("max_iterations must be a positive integer")

    try:
        with localcontext() as context:
            context.prec = WORKING_PRECISION
            context.rounding = ROUND_HALF_UP
            principal = -cash_flows[0]

            def error_at(rate: Decimal) -> Decimal:
                # Reverse evaluation discounts monthly flows without rounding
                # intermediate monetary amounts or constructing calendar dates.
                discounted = Decimal("0")
                for flow in reversed(cash_flows[1:]):
                    discounted = (discounted + flow) / (Decimal("1") + rate)
                return principal - discounted

            def rounded_rates(rate: Decimal) -> CashFlowRates:
                rate = rate.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
                return CashFlowRates(
                    monthly_rate=rate.quantize(RATE_OUTPUT_QUANTUM, rounding=ROUND_HALF_UP),
                    effective_annual_rate=((Decimal("1") + rate) ** 12 - Decimal("1")).quantize(
                        RATE_OUTPUT_QUANTUM, rounding=ROUND_HALF_UP
                    ),
                    annual_nominal_rate=(rate * Decimal("12")).quantize(
                        RATE_OUTPUT_QUANTUM, rounding=ROUND_HALF_UP
                    ),
                )

            lower, upper = Decimal("0"), Decimal("2")
            lower_error, upper_error = error_at(lower), error_at(upper)
            if lower_error == 0:
                rate = lower
            elif upper_error == 0:
                rate = upper
            elif lower_error > 0 or upper_error < 0:
                raise FinanceCalculationError("no monthly rate exists in the interval 0%..200%")
            else:
                for _ in range(max_iterations):
                    rate = (lower + upper) / Decimal("2")
                    error = error_at(rate)
                    if error == 0:
                        break
                    if error > 0:
                        upper = rate
                    else:
                        lower = rate
                    low_rounded = lower.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
                    high_rounded = upper.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
                    if low_rounded == high_rounded:
                        rate = low_rounded
                        break
                    if upper - lower <= RATE_QUANTUM:
                        # Only one rounding boundary can remain. Its error sign
                        # chooses the correctly rounded root without more bisections.
                        boundary = low_rounded + RATE_QUANTUM / Decimal("2")
                        rate = low_rounded if error_at(boundary) > 0 else high_rounded
                        break
                else:
                    raise FinanceCalculationError("rate bisection did not converge")
            return rounded_rates(rate)
    except DecimalException as error:
        raise FinanceCalculationError("Decimal rate calculation failed") from error


@dataclass(frozen=True)
class FinancialPolicy:
    """Standard-library representation of the server-owned Policy contract.

    Pass Policy.model_dump() at the application boundary; no Pydantic is needed
    inside this module. Policy values must never come from untrusted client limits.
    """

    currency: str
    max_discount_pct: str
    min_down_payment_pct: str
    max_installments: int
    max_financing_rate_pct: str
    merchant_discount_rate_pct: str

    def __post_init__(self) -> None:
        if self.currency != "USD":
            raise FinanceValidationError("currency must be USD")
        for value in (
            self.max_discount_pct,
            self.min_down_payment_pct,
            self.max_financing_rate_pct,
            self.merchant_discount_rate_pct,
        ):
            _validate_pct(value)
        _validate_installments(self.max_installments)


def calculate_present_value(cash_flows: list[Decimal], discount_rate_pct: str) -> Decimal:
    """Value monthly flows at t=0, including the immediate flow, rounding once.

    The merchant discount rate is independent of the financing rate. This
    valuation does not use the rounded rate returned by evaluate_cash_flows.
    """
    discount_pct = Decimal(_validate_pct(discount_rate_pct))
    if not isinstance(cash_flows, list) or not 1 <= len(cash_flows) <= 121:
        raise FinanceValidationError("PV requires 1..121 cash flows, starting at t=0")
    for value in cash_flows:
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise FinanceValidationError("PV flows must be finite nonnegative Decimal values")
    try:
        with localcontext() as context:
            context.prec = WORKING_PRECISION
            context.rounding = ROUND_HALF_UP
            discount_rate = discount_pct / Decimal("100")
            value = sum(
                (flow / (Decimal("1") + discount_rate) ** t for t, flow in enumerate(cash_flows)),
                Decimal("0"),
            )
            return value.quantize(CENT, rounding=ROUND_HALF_UP)
    except DecimalException as error:
        raise FinanceCalculationError("Decimal present value calculation failed") from error


def build_alternative(
    *,
    balance: str,
    alternative_type: str,
    terms: dict[str, object],
    policy: FinancialPolicy | dict[str, object],
    pivot_date: date | str,
) -> dict[str, object]:
    """Return a JSON-compatible Alternative matching app.core.schemas.

    Terms must match exactly either SettlementTerms or InstallmentTerms. Rates
    are monthly percentages, never annual fractions. Dates use the supplied
    valuation date, not the invoice's original overdue date. Policy violations
    produce policy_ok=False and RuleHit dictionaries; malformed inputs raise
    FinanceValidationError. Calculation failures raise FinanceCalculationError.

    A blocked alternative is returned as calculation evidence. RecoveryService
    must exclude it from executable offers and build AttemptedAlternative and
    blocked_reasons as required by ProposalOut. No state transitions or PayPal
    calls happen here.
    """
    # schedule depends on the low-level math in this module. Importing here
    # keeps those helpers independently usable without a circular startup import.
    from app.finance.policy import validate
    from app.finance.schedule import _parse_date, build_dated_schedule

    original = money_to_decimal(balance)
    pivot = _parse_date(pivot_date)
    if isinstance(policy, dict):
        try:
            policy = FinancialPolicy(**policy)
        except TypeError as error:
            raise FinanceValidationError("policy fields must match the Policy contract") from error
    if not isinstance(policy, FinancialPolicy):
        raise FinanceValidationError("policy must be FinancialPolicy or a Policy dictionary")
    if not isinstance(terms, dict):
        raise FinanceValidationError("terms must be a dictionary")
    # Policy first: pure limit checks on the terms, before any schedule math.
    violations = validate(terms, policy)

    try:
        with localcontext() as context:
            context.prec = WORKING_PRECISION
            context.rounding = ROUND_HALF_UP
            if alternative_type == "settlement_discount":
                if set(terms) != {"discount_pct"}:
                    raise FinanceValidationError("settlement terms require only discount_pct")
                discount_pct = _validate_pct(terms["discount_pct"])
                discount = (original * Decimal(discount_pct) / Decimal("100")).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
                due_now = original - discount
                schedule = [
                    {
                        "n": 0,
                        "due_date": pivot.isoformat(),
                        "amount": format_money(due_now),
                        "principal": format_money(due_now),
                        "interest": "0.00",
                    }
                ]
                installment_amount = None
            elif alternative_type == "down_payment_installments":
                if set(terms) != {"down_payment_pct", "installments", "periodic_rate_pct"}:
                    raise FinanceValidationError("installment terms must match InstallmentTerms")
                down_pct = _validate_pct(terms["down_payment_pct"])
                count = _validate_installments(terms["installments"])
                rate_pct = _validate_pct(terms["periodic_rate_pct"])
                due_now = (original * Decimal(down_pct) / Decimal("100")).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
                future = build_dated_schedule(
                    format_money(original - due_now), rate_pct, count, pivot
                )
                schedule = [
                    {
                        "n": 0,
                        "due_date": pivot.isoformat(),
                        "amount": format_money(due_now),
                        "principal": format_money(due_now),
                        "interest": "0.00",
                    },
                    *future,
                ]
                installment_amount = future[0]["amount"]
            else:
                raise FinanceValidationError("unknown alternative type")
            flows = [Decimal(row["amount"]) for row in schedule]
            pv = calculate_present_value(flows, policy.merchant_discount_rate_pct)
            return {
                "type": alternative_type,
                "terms": dict(terms),
                "amount_due_now": format_money(due_now),
                "installment_amount": installment_amount,
                "total_paid": format_money(sum(flows, Decimal("0"))),
                "present_value": format_money(pv),
                "financing_cost": format_money(
                    sum((Decimal(row["interest"]) for row in schedule), Decimal("0"))
                ),
                "merchant_difference_vs_balance": format_money(pv - original, signed=True),
                "policy_ok": not violations,
                "violations": violations,
                "schedule": schedule,
            }
    except DecimalException as error:
        raise FinanceCalculationError("Decimal alternative calculation failed") from error


def build_alternatives(
    *,
    balance: str,
    policy: FinancialPolicy | dict[str, object],
    pivot_date: date | str,
    settlement_terms: dict[str, object],
    installment_terms: dict[str, object],
) -> list[dict[str, object]]:
    """Compute both alternatives in contract order; callers must inspect policy_ok."""
    return [
        build_alternative(
            balance=balance,
            policy=policy,
            pivot_date=pivot_date,
            alternative_type=kind,
            terms=terms,
        )
        for kind, terms in (
            ("settlement_discount", settlement_terms),
            ("down_payment_installments", installment_terms),
        )
    ]


_REQUEST_KEYS = frozenset({"engine_version", "invoice", "alternatives", "policy"})
_INVOICE_KEYS = frozenset({"id", "currency", "balance", "due_date", "as_of_date"})
_ALTERNATIVE_FIELDS: dict[str, frozenset[str]] = {
    "settlement_discount": frozenset({"discount_pct"}),
    "down_payment_installments": frozenset(
        {"down_payment_pct", "installments", "periodic_rate_pct"}
    ),
}


def calculate_alternatives(req: Mapping[str, object]) -> dict[str, object]:
    """Contract entry point: EngineRequest in, EngineResult out (pure, no I/O).

    The request carries engine_version, the invoice (balance and as_of_date, which
    is the valuation/payment start date), the requested alternatives and the
    server-owned policy. A policy without currency inherits the invoice currency.
    Policy violations are reported per alternative (policy_ok=False); malformed
    requests raise FinanceValidationError. Unknown request keys are rejected.
    """
    from app.finance.schedule import _parse_date

    if not isinstance(req, Mapping) or set(req) != _REQUEST_KEYS:
        raise FinanceValidationError(
            "request must contain exactly engine_version, invoice, alternatives and policy"
        )
    if req["engine_version"] != ENGINE_VERSION:
        raise FinanceValidationError(f"unsupported engine_version, expected {ENGINE_VERSION}")
    invoice = req["invoice"]
    if not isinstance(invoice, Mapping) or set(invoice) != _INVOICE_KEYS:
        raise FinanceValidationError("invoice must match the EngineRequest invoice fields")
    _parse_date(invoice["due_date"])
    policy = req["policy"]
    if not isinstance(policy, Mapping):
        raise FinanceValidationError("policy must be a dictionary")
    alternatives = req["alternatives"]
    if not isinstance(alternatives, list) or not alternatives:
        raise FinanceValidationError("alternatives must be a non-empty list")

    results = []
    for item in alternatives:
        kind = item.get("type") if isinstance(item, Mapping) else None
        if kind not in _ALTERNATIVE_FIELDS:
            raise FinanceValidationError("unknown alternative type")
        terms = {key: value for key, value in item.items() if key != "type"}
        if set(terms) != _ALTERNATIVE_FIELDS[kind]:
            raise FinanceValidationError(f"{kind} terms do not match the contract fields")
        results.append(
            build_alternative(
                balance=invoice["balance"],
                alternative_type=kind,
                terms=terms,
                policy={"currency": invoice["currency"], **policy},
                pivot_date=invoice["as_of_date"],
            )
        )
    return {"engine_version": ENGINE_VERSION, "alternatives": results}
