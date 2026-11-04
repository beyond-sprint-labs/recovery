# F1-05 financial engine

The production module uses only the Python standard library. Its results are
JSON-compatible dictionaries matching the shared `Alternative` schema. The
application can validate them with its existing Pydantic models at its boundary.

## Public interface

```python
from app.finance.engine import FinanceError, build_alternatives

# Load this from the server, never from client-supplied policy overrides.
policy = {
    "currency": "USD",
    "max_discount_pct": "15",
    "min_down_payment_pct": "20",
    "max_installments": 6,
    "max_financing_rate_pct": "2.0",
    "merchant_discount_rate_pct": "1.0",
}

try:
    alternatives = build_alternatives(
        balance="1000.00",
        pivot_date="2026-11-11",
        policy=policy,  # Existing Policy.model_dump() is also accepted.
        settlement_terms={"discount_pct": "10"},
        installment_terms={
            "down_payment_pct": "30",
            "installments": 3,
            "periodic_rate_pct": "1.5",
        },
    )
except FinanceError as error:
    # Convert to the application's error response at the service boundary.
    print(f"Financial calculation failed: {error}")
```

`build_alternative` has the same balance, policy and date arguments, plus
`alternative_type` and `terms`, to compute a single requested alternative.
`build_alternatives` returns settlement first and installments second.
The caller chooses explicit terms; this module does not infer terms from text.
`pivot_date` is the valuation/payment start date, not automatically the overdue
invoice's original due date.

## Money, rates and dates

- Money enters and leaves as nonnegative strings with exactly two decimals,
  no leading zeros, and at most 12 integer digits. Differences use SignedMoney.
- Calculations use Decimal. Floats are rejected. Monetary rounding is HALF_UP.
- Contractual rates are monthly percentages and are never rounded. `"1.5"`
  means 1.5% per month; the formula uses the fraction `Decimal("0.015")`.
- `Pct` input remains 0..100 with up to four decimal places. Installments are
  strict integers in 1..120. The only supported currency is USD.
- Payments occur at period end. Monthly dates preserve the original day anchor,
  or month end when the pivot is month end, including leap years.
- The down payment is rounded before subtracting it from the original balance.
  It appears at `n=0`, with zero interest. The `installments` count excludes it.
- The settlement discount amount is rounded before subtracting it from balance.
- The regular payment is rounded once. Each period's interest is rounded on the
  current balance. The final payment cancels remaining principal plus interest.
- `installment_amount` is the first financed payment; the final payment can differ.
- PV includes the immediate payment at t=0, discounts future payments with the
  independent merchant rate, and rounds once after summation.
- `total_paid` sums all payments including the immediate one. `financing_cost`
  sums interest. `merchant_difference_vs_balance` is rounded PV minus balance.
- If fixed cent payments would overpay before the final period, calculation
  raises FinanceCalculationError rather than inventing a negative payment.

## Policies and service responsibilities

Comparisons use exact Decimals without rounding rates. Violations are returned
as RuleHit dictionaries with these codes:

| Code | Check |
| --- | --- |
| MAX_DISCOUNT_PCT | Discount exceeds the maximum |
| MIN_DOWN_PAYMENT_PCT | Down payment is below the minimum |
| MAX_INSTALLMENTS | Installments exceed the merchant limit |
| MAX_FINANCING_RATE_PCT | Financing rate exceeds the maximum |

Valid terms outside a merchant limit produce `policy_ok=false` and `violations`.
Malformed terms produce FinanceValidationError. Numerical errors, overflow and
incompatible rounded payments produce FinanceCalculationError. Both inherit
FinanceError. Callers must catch these errors at the service/API boundary.

RecoveryService must not execute a policy-blocked result. It can use `type`,
`terms`, `amount_due_now` and `merchant_difference_vs_balance` to construct
AttemptedAlternative evidence and copy violations into the proposal's blocked
reasons. Proposal states, audit records, text checks, persistence and PayPal calls
belong to their respective services. This module does not change PAID semantics.

## Numerical rate solver

`evaluate_cash_flows` accepts an initial negative Decimal and 1..120 nonnegative
monthly payments, including at least one positive payment. No calendar dates
are used. It searches the inclusive fractional interval [0, 2] by bisection.
Negative later flows are rejected because monotonicity is required.

The internal monthly estimate resolves six decimal places, using at most 21
bisections and one rounding-boundary evaluation if needed. The returned
CashFlowRates fields are Decimal fractions rounded to **four** places with
HALF_UP. Annual rates are calculated from the six-place monthly estimate before
rounding their outputs. These approximate results must not replace an original
contractual rate for policy comparisons. The solver's 200% search bound does not
extend the external Pct input limit of 100%.

## Verification

Run the automated tests from the repository root:

```powershell
python -m pytest tests/unit/finance tests/unit/test_contracts.py
```

The golden test compares both generated alternatives, including all schedule
rows and amounts, with `contracts/examples/proposal_pending.json`. A separate
integration test validates generated outputs with the real shared schemas.
Additional tests cover policy violations, zero rates, full down payments,
rounding, PV, dates, invalid input, overflow and the rate solver.

The original notebook cases have been migrated to automated tests, adapting the
old annual-fraction inputs to periodic percentages and the old 60-payment limit
to the current 120-payment contract. No notebook or plotting packages are needed.
