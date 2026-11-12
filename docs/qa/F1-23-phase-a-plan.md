# F1-23 Phase A - Functional QA Plan

## 1. Purpose

Phase A validates the deterministic functional behaviour of the MVP with the
components already available on `main`: the FastAPI backend, the financial
engine, the proposal lifecycle, the customer portal, the mock PayPal gateway,
the scripted agent, the input sanitizer and the text-number guard.

The goal is not to re-run the existing pytest suite. The goal is to execute the
S01-S12 scenarios through the public HTTP contract, compare the real responses
with the expected business outcomes, and keep reproducible evidence.

## 2. Scope

In scope:

- S01-S12 from `tests/scenarios/scenarios.json`.
- Seed and policy data exposed by the API.
- Proposal creation, policy blocking, clarification, invalid agent output and
  text-number mismatch.
- For `PENDING_MERCHANT` scenarios: merchant approval, customer view, customer
  acceptance, mock PayPal execution, `INVOICING.INVOICE.PAID` webhook and final
  `PAID` state.
- Audit trail and state transitions for the executed flows.

Out of scope (recorded as BLOCKED, not as failures):

- Real PayPal Sandbox payments and real webhook signature verification.
- Real LLM behaviour (F1-20): tone quality and injection resistance with a live
  model.
- Browser/UI E2E (the UI branch is not merged and no frontend is deployed).
- Deployed-environment checks.

## 3. System under test

| Item | Value |
|---|---|
| Repository | `beyond-sprint-labs/recovery` |
| Base | `main` at `162b2ab` |
| QA branch | `qa/f1-23-phase-a` |
| Runtime | Python 3.12 from the repository `.venv` |
| Database | One temporary SQLite database per scenario |
| PayPal | `PAYPAL_MODE=mock` (`MockPayPalGateway`) |
| Agent | `AGENT_MODE=scripted` (`ScriptedAgent`) |
| Demo bootstrap | `APP_ENV=local`, `DEMO_MODE=true` (seeds and links open invoices) |
| HTTP client | FastAPI `TestClient` over the public ASGI contract |

The harness never calls service methods directly. Every validation goes through
`/api/v1` (plus `/health`).

## 4. Test data

Seed invoices:

| Invoice | Balance | Status |
|---|---:|---|
| INV-001 | 1000.00 | OVERDUE |
| INV-002 | 250.50 | OVERDUE |
| INV-003 | 1500.00 | OVERDUE |
| INV-004 | 0.00 | PAID |
| INV-005 | 400.00 | CANCELLED |

Server policy:

| Limit | Value |
|---|---:|
| Currency | USD |
| Max discount | 15% |
| Min down payment | 20% |
| Max installments | 6 |
| Max financing rate | 2.0% |
| Merchant discount rate | 1.0% |

All S01-S12 proposal requests use `INV-001` and a unique `Idempotency-Key`.

## 5. Outcome mapping

The scenario catalog uses business outcomes; the API uses the proposal state
machine plus a typed reason code. The mapping is intentional and follows DEC-05
(`BLOCKED` is a business result and answers HTTP 200):

| Catalog outcome | API status | API reason code |
|---|---|---|
| `PENDING_MERCHANT` | `PENDING_MERCHANT` | none |
| `BLOCKED` | `BLOCKED` | `expected_rule_code` |
| `CLARIFICATION` | `BLOCKED` | `CLARIFICATION_REQUIRED` |
| `INVALID_AGENT_OUTPUT` | `BLOCKED` | `INVALID_AGENT_OUTPUT` |

A scenario passes when the mapped status and reason code match, the response is
HTTP 200, PayPal is not called for blocked flows, and the scenario-specific
checks pass.

## 6. Pass, observation and blocked criteria

- **PASS**: every critical check for the scenario passes.
- **PASS_WITH_OBSERVATION**: the primary business result passes, but a
  non-critical expectation differs. The difference is logged as a defect or
  observation.
- **FAIL**: at least one critical check fails.
- **BLOCKED**: the validation depends on a component that is not available in
  Phase A. Blocked items are listed in the matrix and in
  `F1-23-defects.md`; they are not counted as product failures.

## 7. Execution

From the repository root:

```powershell
.\.venv\Scripts\python.exe docs\qa\run_phase_a.py
```

The harness:

1. Creates an isolated temporary SQLite database for each scenario.
2. Boots the app, which seeds the demo data and links overdue invoices to the
   mock PayPal gateway.
3. Executes the scenario through the HTTP contract.
4. For `PENDING_MERCHANT`, completes approval, customer view, acceptance, mock
   execution, webhook and final-state checks.
5. Writes raw request/response evidence and a `result.json` per scenario.
6. Writes `docs/evidence/F1-23/run-summary.json` and regenerates
   `docs/qa/F1-23-phase-a-matrix.md`.

Customer tokens are single-use and are redacted in the committed evidence.

## 8. Evidence layout

```text
docs/qa/
  F1-23-phase-a-plan.md
  F1-23-phase-a-matrix.md
  F1-23-defects.md
  F1-23-phase-a-report.md
  run_phase_a.py
docs/evidence/F1-23/
  environment.json
  run-summary.json
  SEED/
  S01/ ... S12/
```

Each scenario directory contains the request, the proposal response, and the
flow artefacts that apply (approval, customer view, customer response, webhook,
final proposal, audit events, `result.json`).

## 9. Limitations

- The mock PayPal gateway and the scripted agent are deterministic stand-ins;
  they do not prove real PayPal or real-LLM behaviour.
- The customer token is redacted in evidence; the harness regenerates it on
  every run.
- The evidence reflects one execution. Amounts and state transitions are
  deterministic; proposal IDs, mock invoice IDs and timestamps vary.
