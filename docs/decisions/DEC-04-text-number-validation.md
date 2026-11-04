# DEC-04: Every number in AI-written text is validated before PayPal

- **Status:** Closed
- **Phase:** 1

## Context

A model can alter or invent a figure while the structured output stays correct.

## Decision

`text_guard.check_text_numbers` extracts every number from the generated text and requires each one to exist in the allowed set (engine outputs, intent parameters, policy). Otherwise the proposal becomes `BLOCKED` with `TEXT_NUMBER_MISMATCH`.

## Consequences

Satisfies AC12. The same guard validates the deterministic customer message created at approval time. It checks output only; input hygiene lives in `input_sanitizer` (DEC-25).
