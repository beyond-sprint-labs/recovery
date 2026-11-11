# F1-23 Phase B - Integration and Regression QA Report

## 1. Executive summary

Phase B was executed on 2026-11-11 UTC against `main` at `e86c0b2`, which
includes F1-20 (Gemini agent with audited deterministic fallback) and F1-11
(deployment guide and Sandbox bootstrap tooling). The open UI branch
`origin/feat/ui-final-integration` at `5f88861` was also assessed without
merging it.

Phase B was consolidated into the existing `qa/f1-23-phase-a` branch in merge
commit `080d0fb`; PR #23 carries Phase A and Phase B together.

| Metric | Result |
|---|---:|
| S01-S12 regression | 12 / 12 executed; 12 PASS, including S10 PASS_WITH_OBSERVATION |
| Regression FAIL | 0 |
| Seed/policy validation | PASS |
| F1-20 / F1-11 available-scope probes | 18 / 19 PASS; 1 FAIL (DEF-02) |
| UI production build | FAIL (DEF-03) |
| UI local mock-mode render | PASS (landing page and invoice dashboard) |
| Full pytest suite | 1041 passed, 1 skipped, 53 subtests passed |
| Ruff check / format | PASS |
| Critical defects | 0 |
| High defects | 1 (DEF-03, UI branch build) |
| Medium defects | 1 (DEF-02, deployment guide) |
| Low defects | 2 (DEF-01, DEF-04) |
| Blocked dependencies | 4 (BLK-B01 to BLK-B04) |

The deterministic backend regression is clean: F1-20 and F1-11 did not break
S01-S12. The available F1-20 and F1-11 guards pass. The new findings are a
missing Sandbox bootstrap step in the deployment guide and a TypeScript build
failure in the unmerged UI branch. Real PayPal Sandbox, live Gemini, full UI
E2E and the deployed backend remain blocked.

## 2. Environment and method

| Item | Value |
|---|---|
| Repository | `beyond-sprint-labs/recovery` |
| Base | `main` at `e86c0b2` |
| Execution branch | `qa/f1-23-phase-b` (local), consolidated into `qa/f1-23-phase-a` |
| Consolidation merge | `080d0fb` on `qa/f1-23-phase-a` |
| Phase A reference | `qa/f1-23-phase-a` at `fea5210` |
| Runtime | Python 3.12.15 from the repository `.venv` |
| Database | One temporary SQLite database per scenario |
| PayPal | `PAYPAL_MODE=mock` (`MockPayPalGateway`) |
| Agent | `AGENT_MODE=scripted` for regression; `AGENT_MODE=llm` with dummy config for wiring probes |
| Demo bootstrap | `APP_ENV=local`, `DEMO_MODE=true` for regression |
| HTTP client | FastAPI `TestClient` over the public ASGI contract |
| UI branch | `origin/feat/ui-final-integration` at `5f88861` |
| UI runtime | Node.js 24.14.0, npm 11.9.0, Vite 5.4.2, headless Chrome |

The regression harness imports the Phase A validators, so the S01-S12 checks are
identical to Phase A. Phase A evidence is preserved under
`docs/evidence/F1-23/S01` ... `S12`; Phase B evidence is under
`docs/evidence/F1-23/phase-b/`.

## 3. S01-S12 regression on current `main`

All scenarios were re-executed through `/api/v1` with a fresh database, demo
seed, mock PayPal and scripted agent. The full matrix is
`docs/qa/F1-23-phase-b-matrix.md`.

| ID | Scenario | Catalog outcome | Actual API result | Status |
|---|---|---|---|---|
| SEED | Seed and policy validation | N/A | 5 invoices and policy values match | **PASS** |
| S01 | Partial payment now | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** |
| S02 | Installments request | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** |
| S03 | Exceeds discount | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** |
| S04 | Reasonable discount | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** |
| S05 | Ambiguous amount | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** |
| S06 | Ambiguous date | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** |
| S07 | Hostile tone | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** |
| S08 | Prompt injection | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** |
| S09 | System override | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** |
| S10 | Invalid agent output | INVALID_AGENT_OUTPUT | BLOCKED / `INVALID_AGENT_OUTPUT` | **PASS_WITH_OBSERVATION** |
| S11 | Text-number mismatch | BLOCKED | BLOCKED / `TEXT_NUMBER_MISMATCH` | **PASS** |
| S12 | Sanitizer plus discount | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** |

No regression was observed from F1-20 or F1-11. The S01, S02 and S04 full mock
flows again reached `PAID` through approval, customer acceptance, mock execution
and the `INVOICING.INVOICE.PAID` webhook. S03, S05-S12 again blocked without a
PayPal call and persisted the expected audit events.

## 4. F1-20 available-scope probes

These probes validate wiring and fail-safe behaviour without a live provider.
They do not prove live Gemini quality.

| Probe | Expected | Actual | Status |
|---|---|---|---|
| Startup with `AGENT_MODE=llm` and no `LLM_API_KEY` | Fail closed with `UpstreamError: LLM configuration is incomplete` | Matched | **PASS** |
| `APP_ENV=production` with `DEMO_MODE=true` | Reject the configuration | `ValidationError: DEMO_MODE=true is forbidden` | **PASS** |
| `/health` in `AGENT_MODE=llm` with dummy config | `agent_mode=llm` | `agent_mode=llm` | **PASS** |
| Proposal with `scenario_id=S01_*` in `AGENT_MODE=llm` | Use the scripted path, return `PENDING_MERCHANT` | `PENDING_MERCHANT`; `available_now=300.00` | **PASS** |
| Audit for the scenario override | `PROPOSAL_DRAFTED` present, no `LLM_FALLBACK_ACTIVATED` | Matched | **PASS** |
| F1-20 fallback audit integration tests | 4 tests pass | 4 passed | **PASS** |

The scenario override is selected before `GeminiClient` is constructed, so no
live provider call is made. The F1-20 fallback audit contract is exercised by
the repository's `respx` test double, not by a live provider.

## 5. F1-11 available-scope probes

| Probe | Expected | Actual | Status |
|---|---|---|---|
| Sandbox bootstrap with `PAYPAL_MODE=mock` | Refuse to run | `Sandbox bootstrap requires PAYPAL_MODE=real` | **PASS** |
| Sandbox bootstrap with a non-Sandbox URL | Refuse to run | `refuses to run against a non-Sandbox PayPal URL` | **PASS** |
| Sandbox bootstrap without a Sandbox buyer | Refuse to run | `requires PAYPAL_SANDBOX_BUYER_EMAIL` | **PASS** |
| `.env.example` documents LLM and Sandbox variables | All required names present | Matched | **PASS** |
| `docs/DEPLOY.md` documents the bootstrap command | `python -m app.seed.sandbox_bootstrap` present | Missing | **FAIL (DEF-02)** |
| `docs/DEPLOY.md` documents webhook and buyer variables | Both present | Matched | **PASS** |
| F1-11 bootstrap unit tests | 9 tests pass | 9 passed | **PASS** |

The guard probes prove that the bootstrap tool fails closed before touching the
database or PayPal. They do not prove a real Sandbox bootstrap.

## 6. UI branch smoke

The UI was tested from a temporary detached worktree; the repository was not
switched to the UI branch.

| Check | Expected | Actual | Status |
|---|---|---|---|
| `npm ci` | Exit 0 | Exit 0 | **PASS** |
| `npm run build` | Exit 0 | Exit 1: `src/api/client.ts(85,5): error TS6133: 'mockAuditCursor' is declared but its value is never read.` | **FAIL (DEF-03)** |
| Vite dev server | HTTP 200 | Ready at `http://127.0.0.1:5173` | **PASS** |
| Landing page render | Hero copy present | Present | **PASS** |
| Dashboard render | `Overview` and `INV-001` present | Present | **PASS** |
| Screenshots | Landing and dashboard PNGs | Captured | **PASS** |
| Full UI E2E against backend | Required for Phase C | Not possible: build fails and branch is not integrated | **BLOCKED** |

The local mock-mode render proves that the branch's React/Vite UI can render the
landing page and the invoice dashboard. It does not prove a deployable build or
UI-to-backend integration. The Vercel preview at
`https://ui-neon-alpha.vercel.app` is reachable, but it renders the audit page
for `/` and `/app` and does not match the branch HEAD; it was not used as branch
evidence.

## 7. DEF-01 review

DEF-01 is unchanged on current `main`.

| Field | Result |
|---|---|
| API result | `BLOCKED` / `INVALID_AGENT_OUTPUT` |
| Catalog expected intent | `requested_discount_pct=150` |
| Actual `customer_intent` | All fields `null` |
| Actual `attempted` | `[]` |
| Audit actions | `PROPOSAL_BLOCKED` only |
| Can additional evidence resolve it? | **No** |
| Requires application change? | **Yes, if traceability is required** |

The application correctly rejects the invalid output, but it never stores the
rejected value. Additional QA evidence cannot reconstruct a value the
application does not persist. The decision is therefore either to accept the
limitation explicitly or to add a sanitized attempted-intent field to the
response/audit event. See `docs/evidence/F1-23/phase-b/def-01/analysis.json`.

## 8. Defects

| ID | Severity | Component | Summary | Status |
|---|---|---|---|---|
| DEF-01 | Low | Proposal response / audit | S10 rejects `INVALID_AGENT_OUTPUT` but does not expose the rejected 150% intent. | Open |
| DEF-02 | Medium | `docs/DEPLOY.md` / F1-11 | The deployment guide does not document the required `python -m app.seed.sandbox_bootstrap` step, so a fresh production database has no PayPal-linked invoices. | Open |
| DEF-03 | High (UI branch) | `ui/src/api/client.ts` | `origin/feat/ui-final-integration` fails `npm run build` with TS6133 (`mockAuditCursor` unused). | Open |
| DEF-04 | Low (UI branch) | `ui/src/pages/InvoicesPage.tsx` | The scenario dropdown labels `S02_reasonable_discount` as "Reasonable discount", but the backend maps it to S02 installments and S04 reasonable discount is omitted. | Open |

The complete reproduction steps, impact and recommendations are in
`docs/qa/F1-23-defects.md`.

## 9. Blocked dependencies

| ID | Scope | Dependency | Status |
|---|---|---|---|
| BLK-B01 | Real PayPal Sandbox | Client id/secret, webhook id, merchant email, Sandbox buyer and public HTTPS URL | **BLOCKED** |
| BLK-B02 | Live Gemini LLM | Authorized `LLM_API_KEY` and model | **BLOCKED** (code merged; key missing) |
| BLK-B03 | Full UI integration | Fix DEF-03/DEF-04, merge PR #22 and deploy the UI with the backend | **BLOCKED** |
| BLK-B04 | Deployed backend | Public backend URL and deployment credentials | **BLOCKED** |

## 10. Coverage and limitations

Covered:

- S01-S12 regression on the current `main`.
- Seed and policy data.
- Full mock E2E for S01, S02 and S04.
- F1-20 startup guards, production guard and scenario override.
- F1-20 fallback audit contract through the repository test double.
- F1-11 bootstrap guards and deployment-template completeness.
- UI branch dependency install, build attempt, local mock-mode render and
  screenshots.

Not covered:

- Real Sandbox payment, real webhook signature and real invoice lifecycle.
- Live Gemini output quality, tone and injection resistance.
- UI-to-backend E2E and the customer portal in a browser.
- Deployed-environment checks.
- Multi-invoice flows INV-002/INV-003, performance/load and non-PAID webhook
  event types.

## 11. Recommendation and next steps

1. Fix DEF-03 in `feat/ui-final-integration` and rerun
   `docs/qa/run_phase_b_ui.py`; the production build must pass before PR #22 is
   merged.
2. Fix DEF-04 by aligning the UI scenario options with
   `tests/scenarios/scenarios.json` (`S02_installments_request`,
   `S04_reasonable_discount`).
3. Add the missing bootstrap command and expected output to `docs/DEPLOY.md`
   (DEF-02).
4. Decide whether DEF-01 is accepted as a documented limitation or fixed with a
   sanitized attempted-intent field.
5. Start the real Sandbox phase when BLK-B01 is available; extend the harness
   with real PayPal and webhook signature checks.
6. Start the live LLM phase when BLK-B02 is available; add live S07/S08/S09
   quality and injection checks.
7. Run full UI-to-backend E2E after PR #22 is fixed, merged and deployed
   (BLK-B03/BLK-B04).
8. Keep the three Phase B scripts as repeatable regression and integration
   harnesses.

## 12. Reproduction

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe docs\qa\run_phase_b.py
.\.venv\Scripts\python.exe docs\qa\run_phase_b_platform.py
.\.venv\Scripts\python.exe docs\qa\run_phase_b_ui.py
```

The UI script creates and removes a temporary worktree; it does not switch the
repository to the UI branch. Customer tokens are redacted in committed
evidence.

## 13. Evidence index

| Path | Content |
|---|---|
| `docs/evidence/F1-23/phase-b/environment.json` | Base commit, Phase A reference, Python and settings |
| `docs/evidence/F1-23/phase-b/run-summary.json` | Regression results, DEF-01 analysis and blockers |
| `docs/evidence/F1-23/phase-b/regression/SEED/` | Phase B seed and policy evidence |
| `docs/evidence/F1-23/phase-b/regression/S01/` ... `S12/` | Phase B request/response, flow artefacts, audit and `result.json` |
| `docs/evidence/F1-23/phase-b/platform-summary.json` | F1-20/F1-11 checks and exact subprocess evidence |
| `docs/evidence/F1-23/phase-b/f1-20/` | LLM startup, production guard and scenario override evidence |
| `docs/evidence/F1-23/phase-b/f1-11/` | Sandbox bootstrap guard evidence |
| `docs/evidence/F1-23/phase-b/static/` | Deployment template/guide checks |
| `docs/evidence/F1-23/phase-b/def-01/analysis.json` | DEF-01 decision evidence |
| `docs/evidence/F1-23/phase-b/ui/` | npm logs, Vite logs, DOM, screenshots, UI summary and S02 probe |
| `docs/evidence/F1-23/phase-b/automated/` | Full pytest, targeted tests and Ruff logs |
| `docs/evidence/F1-23/phase-b/automated/final-validation.json` | Final pytest/Ruff exit codes and Phase A preservation check |
| `docs/qa/F1-23-phase-b-matrix.md` | Generated executed matrix |
| `docs/qa/F1-23-defects.md` | Complete defect register and blockers |
