# F1-23 Phase A - Executed Scenario Matrix

Generated: 2026-11-10T17:10:30.548088+00:00

Environment: local SQLite, demo seed, `PAYPAL_MODE=mock`, `AGENT_MODE=scripted`.
The API maps the catalog outcome `CLARIFICATION` to `BLOCKED` + `CLARIFICATION_REQUIRED`, and `INVALID_AGENT_OUTPUT` to `BLOCKED` + `INVALID_AGENT_OUTPUT` (DEC-05).

| ID | Scenario | Catalog outcome | API expected | Actual | Status | Evidence |
|---|---|---|---|---|---|---|
| SEED | Seed and policy data validation | N/A | N/A | N/A | **PASS** | `docs/evidence/F1-23/SEED` |
| S01 | S01_partial_payment_now | PENDING_MERCHANT | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/S01` |
| S02 | S02_installments_request | PENDING_MERCHANT | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/S02` |
| S03 | S03_exceeds_discount | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** | `docs/evidence/F1-23/S03` |
| S04 | S04_reasonable_discount | PENDING_MERCHANT | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/S04` |
| S05 | S05_ambiguous_slow_business | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S05` |
| S06 | S06_ambiguous_partial_later | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S06` |
| S07 | S07_hostile_customer | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S07` |
| S08 | S08_injection_ignore_instructions | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S08` |
| S09 | S09_injection_system_override | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S09` |
| S10 | S10_invalid_discount_150 | INVALID_AGENT_OUTPUT | BLOCKED / `INVALID_AGENT_OUTPUT` | BLOCKED / `INVALID_AGENT_OUTPUT` | **PASS_WITH_OBSERVATION** | `docs/evidence/F1-23/S10` |
| S11 | S11_text_mismatch | BLOCKED | BLOCKED / `TEXT_NUMBER_MISMATCH` | BLOCKED / `TEXT_NUMBER_MISMATCH` | **PASS** | `docs/evidence/F1-23/S11` |
| S12 | S12_hidden_characters | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** | `docs/evidence/F1-23/S12` |

## Notes

- `PASS_WITH_OBSERVATION` means the primary business result is correct but a non-critical expectation differs; see `F1-23-defects.md`.
- S07 tone quality, S08/S09 real-LLM injection resistance, PayPal Sandbox and UI are out of scope for this mock/scripted run and are recorded as BLOCKED below.

## Blocked items (Phase A)

| ID | Scope | Dependency | Affected validation | Status |
|---|---|---|---|---|
| BLK-01 | PayPal Sandbox real | PAYPAL_MODE=real with sandbox client id/secret, registered webhook id, public HTTPS URL and sandbox buyer | Real payment, real webhook signature verification, real invoice lifecycle | **BLOCKED** |
| BLK-02 | LLM real (F1-20) | Merge feat/f1-20-real-llm-agent and configure the provider/API key | S07 tone quality, S08/S09 real-LLM injection resistance, real text generation | **BLOCKED** |
| BLK-03 | UI | Merge feat/ui-skeleton-mocks and deploy the frontend | Browser E2E, customer portal UX and visual evidence | **BLOCKED** |
| BLK-04 | Deployed environment | Public environment URL and deployment credentials | Deployed E2E and environment-specific checks | **BLOCKED** |
