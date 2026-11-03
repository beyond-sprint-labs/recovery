# DEC-02: Money is Decimal in Python and a string in JSON

- **Status:** Closed
- **Phase:** 1

## Context

Binary floats lose precision, and JSON numbers are parsed as floats by most clients, so a monetary value can silently drift.

## Decision

USD only. Amounts and rates use `Decimal` with half-up rounding to 2 decimals and travel as strings: `Money` (non-negative), `SignedMoney` (differences only) and `Pct` (per period, 0..100).

## Consequences

No float ever appears in a contract; `test_contracts.py` rejects float literals in every example. Turning money into a JSON `number` is forbidden in every phase.
