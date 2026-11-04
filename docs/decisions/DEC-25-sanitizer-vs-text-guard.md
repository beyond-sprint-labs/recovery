# DEC-25: Input hygiene and output validation are separate modules

- **Status:** Closed
- **Phase:** 1

## Context

Hidden Unicode in the customer message is a classic injection vector, while numeric drift appears in the model output. They are different problems.

## Decision

`input_sanitizer` runs before the agent: NFKC, removal of Unicode categories Cc (except newline and tab, which become spaces), Cf, Cs, Co and Cn, whitespace collapse and a 500-character cap. It does not try to detect prompt injection with heuristics. `text_guard` validates output numbers only.

## Consequences

A stripped message emits a `WARN` `CONTROL_CHARS_STRIPPED` event and an empty result is a 422 `EMPTY_MESSAGE`. Heuristic injection guarding is a Phase 2 layer chained after the sanitizer.
