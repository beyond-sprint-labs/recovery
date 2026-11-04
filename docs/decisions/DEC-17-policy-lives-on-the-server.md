# DEC-17: Merchant policy lives on the server and never travels in a request

- **Status:** Closed
- **Phase:** 1

## Context

If a client or the AI could send limits, the guardrail would be decorative.

## Decision

`CreateProposalIn` uses `extra="forbid"`, so any `policy` field is a 422. `GET /policy` is read-only. Defaults come from environment variables.

## Consequences

Policy is validated again on `approve` for the chosen alternative. Changing limits means changing server configuration, never a payload.
