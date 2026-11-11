# F1-23 Phase B - Integration and Regression QA Plan

## 1. Purpose

Phase B validates the integration surface that became available after Phase A:

- The S01-S12 deterministic scenarios must keep passing on the current `main`,
  which now includes F1-20 (Gemini agent with audited deterministic fallback)
  and F1-11 (deployment guide and Sandbox bootstrap tooling).
- F1-20 must fail closed when the live LLM configuration is incomplete, and the
  deterministic scenario override must still work in `AGENT_MODE=llm`.
- F1-11 must refuse to bootstrap anything except the real PayPal Sandbox and
  must document the production bootstrap path.
- The open UI branch must be assessed without merging it: production build,
  local mock-mode rendering and visual evidence.
- DEF-01 must be re-checked on the current `main` to decide whether additional
  evidence can close it or an application change is required.

The real PayPal Sandbox, the live Gemini provider and the deployed backend are
not available in this environment. They remain **BLOCKED** and are not counted
as Phase B failures. This plan therefore describes an available-scope Phase B,
not the full real-provider Phase B from the original roadmap.

## 2. Why this scope

Phase A was executed on `main` at `162b2ab`. Since then:

| Change | State | QA consequence |
|---|---|---|
| F1-20 real LLM agent | Merged into `main` (`be258e3`) | The LLM wiring, startup validation and scenario override can be tested without a live key. Live output quality still needs a key. |
| F1-11 deployment / Sandbox bootstrap | Merged into `main` (`e86c0b2`) | The bootstrap guards and deployment template can be tested. Real Sandbox calls still need credentials and a public HTTPS URL. |
| UI final integration | Open branch `origin/feat/ui-final-integration` at `5f88861`; PR #22 open | The branch can be built and rendered locally without merging it. Full UI E2E against the backend waits for the branch to be fixed and integrated. |
| PayPal Sandbox credentials | Not present | Real payment, webhook signature and invoice lifecycle remain blocked. |
| Live LLM API key | Not present | Live intent extraction, tone quality and real-LLM injection resistance remain blocked. |
| Deployed backend URL | Not present | Deployed-environment checks remain blocked. |

This is why Phase B is an **integration and regression phase on the available
code**, not a real-Sandbox phase.

## 3. Scope

In scope:

- Re-run S01-S12 through the public HTTP contract on `main` at `e86c0b2`.
- Validate seed and policy data again.
- Validate the complete mock flow for S01, S02 and S04.
- Validate F1-20 startup guards, production guards and the
  `ALLOW_SCENARIO_ID` override in `AGENT_MODE=llm`.
- Run the F1-20 fallback audit integration tests (test double, not a live
  provider).
- Validate F1-11 Sandbox bootstrap guards and the deployment template.
- Build and render the open UI branch in mock mode; capture DOM, screenshots
  and logs.
- Review DEF-01 on the current code.

Out of scope, recorded as **BLOCKED**:

- Real PayPal Sandbox payment, real webhook signature and real invoice
  lifecycle.
- Live Gemini calls, live tone quality and real-LLM injection resistance.
- Full browser E2E against the real backend and the customer portal.
- Deployed-backend E2E.
- Multi-invoice flows INV-002/INV-003, performance/load and webhook event types
  other than `INVOICING.INVOICE.PAID`.

## 4. System under test

| Item | Value |
|---|---|
| Repository | `beyond-sprint-labs/recovery` |
| Base | `main` at `e86c0b2` (includes F1-20 and F1-11) |
| Execution branch | `qa/f1-23-phase-b` (local) |
| Runtime | Python 3.12.15 from the repository `.venv` |
| Database | One temporary SQLite database per scenario |
| PayPal | `PAYPAL_MODE=mock` (`MockPayPalGateway`) |
| Agent | `AGENT_MODE=scripted` for regression; `AGENT_MODE=llm` with dummy config for wiring probes |
| Demo bootstrap | `APP_ENV=local`, `DEMO_MODE=true` for regression |
| HTTP client | FastAPI `TestClient` over the public ASGI contract |
| UI branch | `origin/feat/ui-final-integration` at `5f88861` |
| UI runtime | Node.js 24.14.0, npm 11.9.0, Vite 5.4.2, headless Chrome |

The regression harness reuses the Phase A validators so the S01-S12 checks are
identical. Phase A evidence remains under `docs/evidence/F1-23/S01` ... `S12`;
Phase B evidence is written under `docs/evidence/F1-23/phase-b/`.

## 5. Test data

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

All S01-S12 requests use `INV-001` and a unique `Idempotency-Key`.

## 6. Outcome mapping

The Phase A mapping is unchanged:

| Catalog outcome | API status | API reason code |
|---|---|---|
| `PENDING_MERCHANT` | `PENDING_MERCHANT` | none |
| `BLOCKED` | `BLOCKED` | `expected_rule_code` |
| `CLARIFICATION` | `BLOCKED` | `CLARIFICATION_REQUIRED` |
| `INVALID_AGENT_OUTPUT` | `BLOCKED` | `INVALID_AGENT_OUTPUT` |

## 7. Pass, observation, fail and blocked criteria

- **PASS**: every critical check for the scenario or probe passes.
- **PASS_WITH_OBSERVATION**: the primary business result passes, but a
  non-critical expectation differs; the difference is logged.
- **FAIL**: at least one critical check fails. A failure caused by an
  unmerged branch is attributed to that branch and does not change the
  `main` regression result.
- **BLOCKED**: the validation needs a provider, credential, deployment or
  branch that is not available. Blocked items are not counted as product
  failures.

## 8. Execution

From the repository root:

```powershell
# Full automated baseline
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .

# S01-S12 regression on the current main
.\.venv\Scripts\python.exe docs\qa\run_phase_b.py

# F1-20 and F1-11 available-scope probes
.\.venv\Scripts\python.exe docs\qa\run_phase_b_platform.py

# UI branch build and local mock-mode smoke
.\.venv\Scripts\python.exe docs\qa\run_phase_b_ui.py
```

Each script writes machine-readable evidence and does not modify application
code. The UI script uses a temporary detached worktree and removes it at the
end; the repository itself is not switched to the UI branch.

## 9. Evidence layout

```text
docs/qa/
  F1-23-phase-b-plan.md
  F1-23-phase-b-matrix.md
  F1-23-phase-b-report.md
  F1-23-defects.md
  run_phase_b.py
  run_phase_b_platform.py
  run_phase_b_ui.py
docs/evidence/F1-23/phase-b/
  environment.json
  run-summary.json
  platform-summary.json
  automated/
  regression/
    SEED/
    S01/ ... S12/
  def-01/
  f1-20/
  f1-11/
  static/
  ui/
```

## 10. Limitations

- The mock PayPal gateway and the scripted agent are deterministic stand-ins;
  they do not prove real PayPal or live-LLM behaviour.
- F1-20 fallback is exercised with the repository's test double (`respx`), not
  a live provider.
- The UI smoke uses mock data. It does not prove the UI-to-backend integration.
- The UI production build currently fails; the local Vite dev render is still
  useful evidence for the rest of the branch, but it is not a deployable build.
- The Vercel preview is reachable but does not match the UI branch HEAD; local
  Vite dev is the source of truth for branch evidence.
- Customer tokens are redacted in committed evidence.
