# DEC-05: BLOCKED is a business result and returns HTTP 200

- **Status:** Closed
- **Phase:** 1

## Context

A blocked proposal is the product working as designed, not a protocol failure.

## Decision

`POST /invoices/{id}/proposals` returns 200 with a structured `ProposalOut` and a `CRITICAL` audit event when policy or the text guard blocks the proposal.

## Consequences

The UI renders BLOCKED as data in the audit grid. 4xx/5xx stay reserved for validation (422), unknown ids (404), invalid transitions (409) and PayPal failures that changed no state (502).
