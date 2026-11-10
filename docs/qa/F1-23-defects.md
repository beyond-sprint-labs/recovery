# F1-23 Phase A - Defects and Blocked Items

## 1. Summary

| Severity | Open | Closed | Notes |
|---|---:|---:|---|
| Critical | 0 | 0 | No policy bypass, double charge or data loss observed. |
| High | 0 | 0 | No broken core flow observed. |
| Medium | 0 | 0 | No medium-severity functional defect observed. |
| Low | 1 | 0 | S10 audit/debug traceability observation. |

Phase A result: **11 of 12 scenarios PASS, S10 is PASS_WITH_OBSERVATION, 0
FAIL**; the seed/policy validation also passes. The only observation is
non-blocking and does not change the correct `INVALID_AGENT_OUTPUT` block.

## 2. Defect log

### DEF-01 - S10 invalid agent output does not expose the rejected intent

| Field | Value |
|---|---|
| ID | DEF-01 |
| Severity | Low |
| Status | Open |
| Scenario | S10 - invalid agent output (150% discount) |
| Component | Proposal response / audit traceability |
| Detected in | `qa/f1-23-phase-a` |
| Evidence | `docs/evidence/F1-23/S10/02-proposal-response.json`, `docs/evidence/F1-23/S10/08-audit-events.json`, `docs/evidence/F1-23/S10/result.json` |

**Steps to reproduce**

1. Start the app with the Phase A environment (`APP_ENV=local`,
   `DEMO_MODE=true`, `PAYPAL_MODE=mock`, `AGENT_MODE=scripted`).
2. Send `POST /api/v1/invoices/INV-001/proposals` with the S10 message and
   `scenario_id: "S10_invalid_agent_output"` plus a unique `Idempotency-Key`.
3. Inspect the HTTP 200 response.

**Expected**

The proposal is blocked with `INVALID_AGENT_OUTPUT` (the primary business
result), and the rejected 150% discount is traceable for audit/debugging, as
suggested by the scenario catalog's `expected_intent`.

**Actual**

- HTTP 200, `status: "BLOCKED"`, `blocked_reasons[0].code:
  "INVALID_AGENT_OUTPUT"`.
- `customer_intent` is all `null`.
- `attempted` is `[]`.
- The audit trail records the block, but not the rejected `150` value.

**Impact**

No policy bypass: the invalid output is correctly rejected before the engine
or PayPal. The gap is audit/debug traceability: an operator cannot see which
invalid value the agent produced from the proposal response or the audit
payload.

**Recommendation**

If the response contract allows it, expose a sanitized `attempted_intent` or a
rule `attempted` value in the `INVALID_AGENT_OUTPUT` audit event. Otherwise,
document explicitly that invalid agent output is intentionally not echoed.

## 3. Observations (not defects)

| ID | Observation | Disposition |
|---|---|---|
| OBS-01 | The catalog outcome `CLARIFICATION` maps to API `BLOCKED` + `CLARIFICATION_REQUIRED`; `INVALID_AGENT_OUTPUT` maps to `BLOCKED` + code. | Expected per DEC-05 and the proposal state machine; validated in S05-S10. |
| OBS-02 | S01/S02/S04 offer both `settlement_discount` and `down_payment_installments`. When the customer does not supply a down payment, the engine uses the server default 30% and a 1.5% periodic rate. | Expected product behaviour; documented in the scenario catalog notes. |
| OBS-03 | S11 `text_number_check.numbers_in_text` contains duplicate numbers because the guard checks both the explanation and the customer draft; `unmatched` is correct (`850.00`). | No functional impact; the block is correct and the draft/explanation are suppressed. |
| OBS-04 | PayPal execution audit events (`PAYPAL_DRAFT_CREATED`, etc.) have `state_from`/`state_to` as `null`; proposal-level transitions are captured by `EXECUTION_STARTED` and `EXECUTION_COMPLETED`. | Acceptable audit model; the state machine trail is complete. |
| OBS-05 | S07 tone quality and S08/S09 real-LLM injection resistance cannot be assessed with the scripted agent. | BLOCKED on F1-20 / real LLM; see BLK-02. |

## 4. Blocked items

These are dependencies, not product failures. They are excluded from the Phase A
pass/fail count and must be executed in Phase B/C.

| ID | Scope | Dependency | Affected validation | Status |
|---|---|---|---|---|
| BLK-01 | PayPal Sandbox real | `PAYPAL_MODE=real` with sandbox client id/secret, registered webhook id, public HTTPS URL and sandbox buyer | Real payment, real webhook signature verification, real invoice lifecycle | **BLOCKED** |
| BLK-02 | LLM real (F1-20) | Merge `feat/f1-20-real-llm-agent` and configure the provider/API key | S07 tone quality, S08/S09 real-LLM injection resistance, real text generation | **BLOCKED** |
| BLK-03 | UI | Merge `feat/ui-skeleton-mocks` and deploy the frontend | Browser E2E, customer portal UX and visual evidence | **BLOCKED** |
| BLK-04 | Deployed environment | Public environment URL and deployment credentials | Deployed E2E and environment-specific checks | **BLOCKED** |

## 5. Exit criteria

Phase A is complete for the available components:

- All S01-S12 scenarios executed through the public HTTP contract.
- Seed and policy data validated.
- Full mock flow validated for S01, S02 and S04.
- No critical, high or medium defects.
- One low-severity traceability observation (DEF-01).
- Four dependencies explicitly blocked.

Phase B can start when PayPal Sandbox credentials and a public HTTPS webhook URL
are available. Phase C can start when F1-20 and the UI branch are merged and
deployed.
