# F1-23 Phase A - Functional QA Report

## 1. Executive summary

Phase A of F1-23 was executed on 2026-11-10 against the public HTTP contract
with the demo seed, the mock PayPal gateway and the scripted agent.

| Metric | Result |
|---|---:|
| Scenarios executed | 12 / 12 (S01-S12) |
| Scenario PASS | 11 |
| Scenario PASS_WITH_OBSERVATION | 1 (S10) |
| Scenario FAIL | 0 |
| Seed/policy validation | PASS |
| Evidence entries | 13 (SEED + S01-S12) |
| Critical / High / Medium defects | 0 / 0 / 0 |
| Low-severity observations | 1 (DEF-01) |
| Blocked dependencies | 4 (BLK-01 to BLK-04) |

Phase A exit criteria are met for the components currently available on `main`.
No policy bypass, double charge or broken proposal flow was observed. The only
finding is a low-severity audit traceability observation in S10.

## 2. Environment and method

| Item | Value |
|---|---|
| Repository | `beyond-sprint-labs/recovery` |
| Base | `main` at `162b2ab` |
| QA branch | `qa/f1-23-phase-a` |
| Runtime | Python 3.12.15 from the repository `.venv` |
| Database | One temporary SQLite database per scenario |
| PayPal | `PAYPAL_MODE=mock` (`MockPayPalGateway`) |
| Agent | `AGENT_MODE=scripted` (`ScriptedAgent`) |
| Demo bootstrap | `APP_ENV=local`, `DEMO_MODE=true` |
| HTTP client | FastAPI `TestClient` over the public ASGI contract |

The harness does not call service methods directly. Every scenario goes through
`/api/v1` (plus `/health`). Each scenario starts from a fresh database seeded by
the demo bootstrap, uses `INV-001`, and sends a unique `Idempotency-Key`.

For `PENDING_MERCHANT` scenarios the harness completes the whole flow:

1. Create proposal.
2. Approve one alternative.
3. Open the customer view with the issued token.
4. Accept as the customer.
5. Execute against the mock PayPal gateway.
6. Send an `INVOICING.INVOICE.PAID` webhook.
7. Confirm the final `PAID` state and the audit trail.

For blocked/clarification scenarios it validates HTTP 200, the mapped status and
reason code, the absence of alternatives, `paypal_called: false`, the relevant
policy/text checks and the audit event.

## 3. Executed matrix

| ID | Scenario | Catalog outcome | Actual API result | Status | Evidence |
|---|---|---|---|---|---|
| SEED | Seed and policy data validation | N/A | 5 invoices, policy values match | **PASS** | `docs/evidence/F1-23/SEED` |
| S01 | Partial payment now | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/S01` |
| S02 | Installments request | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/S02` |
| S03 | Exceeds discount | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** | `docs/evidence/F1-23/S03` |
| S04 | Reasonable discount | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/S04` |
| S05 | Ambiguous amount | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S05` |
| S06 | Ambiguous date | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S06` |
| S07 | Hostile tone | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S07` |
| S08 | Prompt injection | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S08` |
| S09 | System override | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/S09` |
| S10 | Invalid agent output | INVALID_AGENT_OUTPUT | BLOCKED / `INVALID_AGENT_OUTPUT` | **PASS_WITH_OBSERVATION** | `docs/evidence/F1-23/S10` |
| S11 | Text-number mismatch | BLOCKED | BLOCKED / `TEXT_NUMBER_MISMATCH` | **PASS** | `docs/evidence/F1-23/S11` |
| S12 | Sanitizer + discount | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** | `docs/evidence/F1-23/S12` |

The generated version with the full check counts is
`docs/qa/F1-23-phase-a-matrix.md`.

## 4. Evidence highlights

### 4.1 Seed and policy data (SEED)

- `/health`: `status=ok`, `demo_mode=true`, `paypal_mode=mock`,
  `agent_mode=scripted`.
- `/invoices`: INV-001 1000.00 OVERDUE, INV-002 250.50 OVERDUE, INV-003
  1500.00 OVERDUE, INV-004 0.00 PAID, INV-005 400.00 CANCELLED.
- Overdue invoices are linked to the mock PayPal gateway.
- `/policy`: USD, max discount 15%, min down payment 20%, max installments 6,
  max financing rate 2.0%, merchant discount rate 1.0%.
- No customer email is exposed by the invoice list.

### 4.2 S01 - partial payment now

- Intent: `available_now=300.00`, `preferred_installments=3`.
- Settlement alternative: 900.00 due now, 10% discount, merchant difference
  `-100.00`.
- Installment alternative: 300.00 now, three installments of 240.37 / 240.37 /
  240.36, total paid 1021.10, present value 1006.91, merchant difference 6.91.
- Approved alternative: `down_payment_installments`.
- Customer view: 300.00 now, 240.37 installment, 1021.10 total, status
  `PENDING_CUSTOMER`.
- Execution: `EXECUTED`, mock invoice `MOCK-INV-C4FC90B3`, steps
  `preflight_ok`, `draft_created`, `original_cancelled`, `draft_sent`.
- Webhook `INVOICING.INVOICE.PAID`: final status `PAID`.
- Audit trail: `PROPOSAL_DRAFTED` -> `PROPOSAL_APPROVED` ->
  `CUSTOMER_LINK_ISSUED` -> `CUSTOMER_ACCEPTED` -> `EXECUTION_STARTED` ->
  `PAYPAL_DRAFT_CREATED` -> `PAYPAL_ORIGINAL_CANCELLED` ->
  `PAYPAL_INVOICE_SENT` -> `EXECUTION_COMPLETED` -> `PAYMENT_CONFIRMED`.

### 4.3 S02 - installments request

- Intent: `preferred_installments=3`, no `available_now`.
- The engine applies the server default 30% down payment: 300.00 now, three
  installments of 240.37 / 240.37 / 240.36, total 1021.10, present value
  1006.91.
- Approved `down_payment_installments`; full mock flow reached `PAID`.
- This default fill is expected and documented in the scenario catalog notes.

### 4.4 S03 - discount above policy

- Intent: 40% requested; policy limit 15%.
- HTTP 200, `BLOCKED`, reason `MAX_DISCOUNT_PCT`.
- Attempted alternative captured: 600.00 due now, merchant difference
  `-400.00`.
- No alternatives offered; `paypal_called=false`; `PROPOSAL_BLOCKED` audited.

### 4.5 S04 - reasonable discount

- Intent: 10% requested.
- Settlement alternative: 900.00 due now, 10% discount, merchant difference
  `-100.00`.
- Approved `settlement_discount`; customer view showed 900.00; full mock flow
  reached `PAID`.

### 4.6 S05-S09 - clarification paths

- S05 (ambiguous amount), S06 (ambiguous date), S07 (hostile tone), S08 (prompt
  injection) and S09 (system override) all returned HTTP 200, `BLOCKED` with
  `CLARIFICATION_REQUIRED`.
- No alternatives, no PayPal call, `PROPOSAL_BLOCKED` audit event.
- The deterministic clarification path passes. S07 tone quality and S08/S09
  real-LLM injection resistance remain blocked on F1-20.

### 4.7 S10 - invalid agent output

- HTTP 200, `BLOCKED`, reason `INVALID_AGENT_OUTPUT`.
- No alternatives, no PayPal call, `PROPOSAL_BLOCKED` audit event.
- The block is correct, but the rejected 150% value is not exposed:
  `customer_intent` is all `null` and `attempted` is empty. This is DEF-01
  (Low). See `docs/qa/F1-23-defects.md`.

### 4.8 S11 - text-number mismatch

- HTTP 200, `BLOCKED`, reason `TEXT_NUMBER_MISMATCH`.
- `text_number_check.status=FAILED`; `unmatched=["850.00"]`; policy check
  passed.
- `explanation` and `customer_message_draft` are `null`; no PayPal call.
- The agent tried to add an unsupported `$850.00`; the guard blocked it.

### 4.9 S12 - sanitizer plus discount

- The input contained a zero-width control character in `40%`.
- The sanitizer removed it and recorded `INPUT_SANITIZED` with
  `CONTROL_CHARS_STRIPPED` (1 character).
- The resulting 40% request exceeded the 15% policy and was blocked with
  `MAX_DISCOUNT_PCT`.
- Audit trail: `INPUT_SANITIZED` + `PROPOSAL_BLOCKED`; no PayPal call.

## 5. Defects

| ID | Severity | Scenario | Summary | Status |
|---|---|---|---|---|
| DEF-01 | Low | S10 | The rejected 150% intent is not exposed in the response or audit payload. | Open |

No Critical, High or Medium defects were found. The complete defect log,
reproduction steps and recommendations are in `docs/qa/F1-23-defects.md`.

## 6. Blocked dependencies

| ID | Scope | Dependency | Affected validation |
|---|---|---|---|
| BLK-01 | PayPal Sandbox real | Sandbox credentials, webhook id, public HTTPS URL and buyer | Real payment and real webhook verification |
| BLK-02 | LLM real (F1-20) | Merge `feat/f1-20-real-llm-agent` and configure the provider key | S07 tone, S08/S09 real-LLM injection resistance |
| BLK-03 | UI | Merge `feat/ui-skeleton-mocks` and deploy the frontend | Browser E2E and visual evidence |
| BLK-04 | Deployed environment | Public URL and deployment credentials | Deployed E2E |

These are not Phase A failures; they require Phase B/C access.

## 7. Coverage and limitations

Covered in Phase A:

- 12/12 scenarios at the public API level.
- Full mock E2E for the three `PENDING_MERCHANT` scenarios (S01, S02, S04).
- All blocked/clarification paths (S03, S05-S12).
- Seed and policy data integrity.
- State transitions and audit trail for the full mock flow.

Not covered in Phase A:

- Real PayPal Sandbox payment and real webhook signature verification.
- Real LLM output quality, tone and injection resistance.
- Browser/UI E2E and visual evidence.
- Deployed-environment checks.
- Multi-invoice flows INV-002/INV-003, performance/load and webhook event types
  other than `INVOICING.INVOICE.PAID`.

## 8. Recommendation and next steps

1. Accept Phase A as the deterministic baseline; no blocking defect was found.
2. Decide whether DEF-01 is accepted as a documented limitation or fixed by
   exposing a sanitized attempted intent in the invalid-agent-output audit.
3. Start Phase B when PayPal Sandbox credentials and a public HTTPS webhook URL
   are available.
4. Start Phase C when F1-20 and the UI branch are merged and deployed.
5. Keep `docs/qa/run_phase_a.py` as a repeatable regression harness; it can be
   wired into CI after the QA branch is merged.

## 9. Reproduction

From the repository root:

```powershell
.\.venv\Scripts\python.exe docs\qa\run_phase_a.py
```

The command regenerates `docs/evidence/F1-23/` and
`docs/qa/F1-23-phase-a-matrix.md`. Customer tokens are redacted in the committed
evidence.

## 10. Evidence index

| Path | Content |
|---|---|
| `docs/evidence/F1-23/environment.json` | Commit, branch, Python and settings used |
| `docs/evidence/F1-23/run-summary.json` | Machine-readable results and blocked items |
| `docs/evidence/F1-23/SEED/` | Health, invoices and policy evidence |
| `docs/evidence/F1-23/S01/` ... `S12/` | Request/response, flow artefacts, audit and `result.json` |
| `docs/qa/F1-23-phase-a-matrix.md` | Generated executed matrix |
| `docs/qa/F1-23-defects.md` | Defect log and blocked dependencies |
