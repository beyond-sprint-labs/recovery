# DEC-29: Hardened numeric types and the meaning of PAID for installments

- **Status:** Closed
- **Phase:** 1

## Context

Python's `\d` accepts non-ASCII digits, which `Decimal` can parse, so a loose pattern is a validation bypass. A partial-payment state would leave proposals unfinished.

## Decision

All patterns use ASCII `[0-9]`. `Money` is non-negative with no leading zeros and exactly 2 decimals, `SignedMoney` is reserved for differences, `Pct` is 0..100 and `Installments` is 1..120. For the installments alternative, `PAID` means the first scheduled payment was confirmed and the UI says so.

## Consequences

A `Pct` of `"150"` is `INVALID_AGENT_OUTPUT`, while `"100"` is valid and blocked by `MAX_DISCOUNT_PCT`. There is no `PARTIALLY_PAID` state in Phase 1; adding one later is a new state and must not alter existing transitions.
