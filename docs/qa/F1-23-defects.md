# F1-23 - Defects and Blocked Items (Phase A + Phase B)

## 1. Summary

| Severity | Open | Closed | Notes |
|---|---:|---:|---|
| Critical | 0 | 0 | No policy bypass, double charge or data loss observed. |
| High | 1 | 0 | DEF-03: the unmerged UI branch cannot produce a production build. |
| Medium | 1 | 0 | DEF-02: the deployment guide omits the Sandbox bootstrap step. |
| Low | 2 | 0 | DEF-01 traceability and DEF-04 UI scenario label mismatch. |

Phase A result: **11 of 12 scenarios PASS, S10 is PASS_WITH_OBSERVATION, 0
FAIL**; seed/policy validation passes.

Phase B result: **12 of 12 scenarios PASS on current `main` (S10 is
PASS_WITH_OBSERVATION), 0 FAIL**; the available F1-20/F1-11 probes pass except
for the deployment-guide check (DEF-02), and the UI branch has a build failure
(DEF-03). No Critical defect was found.

The High and Medium findings are in the unmerged UI branch and the deployment
documentation, not in the backend runtime on `main`.

## 2. Defect log

### DEF-01 - S10 invalid agent output does not expose the rejected intent

| Field | Value |
|---|---|
| ID | DEF-01 |
| Severity | Low |
| Status | Open |
| Scenario | S10 - invalid agent output (150% discount) |
| Component | Proposal response / audit traceability |
| Detected in | `qa/f1-23-phase-a`; re-checked in `qa/f1-23-phase-b` |
| Evidence | `docs/evidence/F1-23/S10/02-proposal-response.json`, `docs/evidence/F1-23/S10/08-audit-events.json`, `docs/evidence/F1-23/phase-b/def-01/analysis.json` |

**Steps to reproduce**

1. Start the app with `APP_ENV=local`, `DEMO_MODE=true`,
   `PAYPAL_MODE=mock`, `AGENT_MODE=scripted`.
2. Send `POST /api/v1/invoices/INV-001/proposals` with the S10 message and
   `scenario_id: "S10_invalid_discount_150"` plus a unique
   `Idempotency-Key`.
3. Inspect the HTTP 200 response and the proposal audit events.

**Expected**

The proposal is blocked with `INVALID_AGENT_OUTPUT`, and the rejected 150%
discount is traceable for audit/debugging, as suggested by the scenario
catalog's `expected_intent`.

**Actual**

- HTTP 200, `status: "BLOCKED"`, `blocked_reasons[0].code:
  "INVALID_AGENT_OUTPUT"`.
- `customer_intent` is all `null`.
- `attempted` is `[]`.
- The audit trail records `PROPOSAL_BLOCKED`, but not the rejected `150` value.

**Impact**

No policy bypass: the invalid output is correctly rejected before the engine or
PayPal. The gap is audit/debug traceability: an operator cannot see which
invalid value the agent produced from the proposal response or the audit
payload.

**Phase B conclusion**

Additional QA evidence cannot resolve the gap because the application never
stores the rejected value. The decision is either to accept the limitation
explicitly or to add a sanitized attempted-intent field to the response/audit
event.

### DEF-02 - Deployment guide omits the Sandbox bootstrap step

| Field | Value |
|---|---|
| ID | DEF-02 |
| Severity | Medium |
| Status | Open |
| Component | `docs/DEPLOY.md` (F1-11) |
| Detected in | `qa/f1-23-phase-b` on `main` at `e86c0b2` |
| Evidence | `docs/evidence/F1-23/phase-b/static/f1-11-config-checks.json`, `docs/evidence/F1-23/phase-b/platform-summary.json`, `docs/DEPLOY.md` section 7 |

**Steps to reproduce**

1. Follow `docs/DEPLOY.md` on a fresh production database with
   `APP_ENV=production`, `DEMO_MODE=false`, `PAYPAL_MODE=real`.
2. Configure the environment and start the service as documented.
3. Do not run any additional command not present in the guide.
4. Call `GET /api/v1/invoices` and attempt a customer ACCEPT flow.

**Expected**

The guide explicitly tells the operator to run
`python -m app.seed.sandbox_bootstrap` after the environment is configured and
before confirming the seeded invoices. The command seeds the database and opens
one original invoice per overdue seed invoice in the PayPal Sandbox.

**Actual**

- `docs/DEPLOY.md` section 7 step 4 only says "Confirm the seeded invoices are
  visible" and shows `curl -s .../api/v1/invoices`.
- The guide does not contain the `python -m app.seed.sandbox_bootstrap` command.
- With `DEMO_MODE=false`, the demo bootstrap does not seed the database. A fresh
  production database is therefore empty, and an invoice without
  `paypal_invoice_id` fails the customer ACCEPT step with
  `INVOICE_NOT_LINKED_TO_PAYPAL`.

**Impact**

A deployment that follows the guide literally starts with an empty grid and a
broken customer ACCEPT path. The tool exists and its module docstring documents
the command, so the workaround is discoverable, but the primary deployment path
is incomplete.

**Recommendation**

Add the bootstrap command, its guard conditions and the expected JSON report to
`docs/DEPLOY.md`; mention `--relink-stale` for cancelled or paid originals.
No application code change is required.

### DEF-03 - UI branch production build fails on an unused mock cursor

| Field | Value |
|---|---|
| ID | DEF-03 |
| Severity | High (UI branch) |
| Status | Open |
| Component | `ui/src/api/client.ts` in `origin/feat/ui-final-integration` |
| Detected in | `qa/f1-23-phase-b` UI smoke |
| Evidence | `docs/evidence/F1-23/phase-b/ui/npm-build.log`, `docs/evidence/F1-23/phase-b/ui/ui-summary.json` |

**Steps to reproduce**

1. Create a temporary worktree at `origin/feat/ui-final-integration` (`5f88861`).
2. Run `npm ci` in `ui/`.
3. Run `npm run build`.

**Expected**

`tsc -b && vite build` exits 0 and produces a deployable `dist/`.

**Actual**

```text
src/api/client.ts(85,5): error TS6133: 'mockAuditCursor' is declared but its value is never read.
```

`npm run build` exits 1 before Vite produces a bundle. Vite dev still renders
the UI, but the production build and any CI/deploy step that runs
`npm run build` fail.

**Impact**

The UI branch cannot be built or deployed as-is. This blocks full UI E2E and
the Phase C UI deliverable. It does not affect the backend `main` runtime.

**Recommendation**

Remove `mockAuditCursor` or use it as the mock audit stream cursor, then rerun
`npm run build` and the UI CI job before merging PR #22.

### DEF-04 - UI scenario label maps to the wrong catalog scenario

| Field | Value |
|---|---|
| ID | DEF-04 |
| Severity | Low (UI branch) |
| Status | Open |
| Component | `ui/src/pages/InvoicesPage.tsx` scenario dropdown |
| Detected in | `qa/f1-23-phase-b` UI review and API probe |
| Evidence | `docs/evidence/F1-23/phase-b/ui/s02-ui-scenario-contract.json`, `tests/scenarios/scenarios.json` |

**Steps to reproduce**

1. Open the invoice dashboard on the UI branch.
2. Inspect the scenario dropdown.
3. Select `S02_reasonable_discount` ("Reasonable discount") and create a
   proposal.
4. Inspect the response intent and alternatives.

**Expected**

The dropdown should use the official catalog IDs and labels:
`S02_installments_request` (installments) and `S04_reasonable_discount`
(reasonable discount).

**Actual**

- The UI offers `S02_reasonable_discount` with the label "Reasonable discount".
- The backend `scenario_key` maps `S02_reasonable_discount` to `S02`, whose
  scripted intent is `preferred_installments=3`; the response contains
  `customer_intent.preferred_installments=3` and no requested discount.
- The UI does not offer `S04_reasonable_discount`.

**Impact**

The demo label is misleading and selecting S02 does not exercise the reasonable
discount scenario. Both alternatives are still offered, so the functional
impact is low, but the demo operator can draw the wrong conclusion.

**Recommendation**

Align the dropdown with `tests/scenarios/scenarios.json`; use
`S02_installments_request` and add `S04_reasonable_discount`.

## 3. Observations (not defects)

| ID | Observation | Disposition |
|---|---|---|
| OBS-01 | The catalog outcome `CLARIFICATION` maps to API `BLOCKED` + `CLARIFICATION_REQUIRED`; `INVALID_AGENT_OUTPUT` maps to `BLOCKED` + code. | Expected per DEC-05 and the proposal state machine; validated in S05-S10. |
| OBS-02 | S01/S02/S04 offer both `settlement_discount` and `down_payment_installments`. When the customer does not supply a down payment, the engine uses the server default 30% and a 1.5% periodic rate. | Expected product behaviour; documented in the scenario catalog notes. |
| OBS-03 | S11 `text_number_check.numbers_in_text` contains duplicate numbers because the guard checks both the explanation and the customer draft; `unmatched` is correct (`850.00`). | No functional impact; the block is correct and the draft/explanation are suppressed. |
| OBS-04 | PayPal execution audit events (`PAYPAL_DRAFT_CREATED`, etc.) have `state_from`/`state_to` as `null`; proposal-level transitions are captured by `EXECUTION_STARTED` and `EXECUTION_COMPLETED`. | Acceptable audit model; the state machine trail is complete. |
| OBS-05 | S07 tone quality and S08/S09 real-LLM injection resistance cannot be assessed with the scripted agent. | BLOCKED on a live LLM key; see BLK-B02. |
| OBS-B01 | Phase B regression on `main` at `e86c0b2` produced the same S01-S12 results as Phase A, with no regression from F1-20/F1-11. | Expected; the deterministic baseline is stable. |
| OBS-B02 | F1-20 startup and production guards fail closed without a live key; the scenario override still returns `PENDING_MERCHANT` and does not emit `LLM_FALLBACK_ACTIVATED`. | PASS; live LLM quality remains blocked. |
| OBS-B03 | F1-11 Sandbox bootstrap refuses mock mode, non-Sandbox URLs and a missing Sandbox buyer before touching the database or PayPal. | PASS; real Sandbox bootstrap remains blocked. |
| OBS-B04 | The Vercel preview `https://ui-neon-alpha.vercel.app` returns HTTP 200 but renders the audit page for `/` and `/app`; it does not match the branch HEAD. | Preview is stale/misconfigured; branch evidence uses local Vite dev, not the preview. |

## 4. Blocked items

These are dependencies, not product failures. They are excluded from the Phase B
pass/fail count and must be executed when the dependency is available.

| ID | Scope | Dependency | Affected validation | Status |
|---|---|---|---|---|
| BLK-B01 | PayPal Sandbox real | `PAYPAL_MODE=real` with Sandbox client id/secret, registered webhook id, merchant email, Sandbox buyer and public HTTPS URL | Real payment, real webhook signature, real invoice lifecycle | **BLOCKED** |
| BLK-B02 | Live Gemini LLM | Authorized `LLM_API_KEY` and model | Live intent extraction, tone quality, real-LLM injection resistance | **BLOCKED** (code merged; key missing) |
| BLK-B03 | Full UI integration | Fix DEF-03/DEF-04, merge PR #22 and deploy the UI with the backend | Full browser E2E, customer portal UX, UI-to-backend integration | **BLOCKED** |
| BLK-B04 | Deployed backend | Public backend URL and deployment credentials | Deployed-environment E2E | **BLOCKED** |

## 5. Exit criteria

Phase B is complete for the available components:

- S01-S12 re-executed through the public HTTP contract on current `main`.
- Seed and policy data revalidated.
- Full mock flow revalidated for S01, S02 and S04.
- F1-20 and F1-11 available-scope guards validated.
- UI branch built, rendered and visually evidenced; build failure recorded.
- DEF-01 rechecked and classified as requiring an application change if
  traceability is required.
- Four dependencies explicitly blocked.

Phase B is **not** a real-Sandbox or live-LLM sign-off. Those require the
credentials and public URL listed in BLK-B01/BLK-B02.
