# DEC-03: Balance and date come from the invoice, limits from the policy, the AI only supplies intent

- **Status:** Closed
- **Phase:** 1

## Context

Any figure the model can choose or see is a surface for financial hallucination.

## Decision

The service builds a `tool_runner` closure that injects balance, date and policy from the server. The agent only reports the terms the customer asked for (`CustomerIntent`).

## Consequences

The agent never receives or picks a balance, a date or a limit. Every number in the output traces back to the invoice, the policy or the finance engine.
