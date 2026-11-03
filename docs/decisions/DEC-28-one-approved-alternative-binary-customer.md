# DEC-28: The merchant approves ONE alternative and the customer only accepts or declines

- **Status:** Closed
- **Phase:** 1

## Context

Letting the customer compare or renegotiate reopens the attack surface and the UI scope we cut in DEC-14.

## Decision

`approve` pre-approves a single alternative with `policy_ok=true`. `CustomerProposalView` exposes only that alternative and forbids internal fields. The final message is a deterministic template validated by `text_guard`. The token is stored as a SHA-256 hash and consumed by a compare-and-set.

## Consequences

Double clicks produce one execution. DECLINE is terminal and never calls PayPal. The raw token appears only in the approve response.
