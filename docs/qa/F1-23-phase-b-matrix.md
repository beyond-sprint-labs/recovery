# F1-23 Phase B - Executed Matrix

Generated: 2026-11-11T01:00:05.050315+00:00

Base: `main` at `e86c0b2` (includes F1-20 and F1-11).
Consolidated into `qa/f1-23-phase-a` at merge commit `080d0fb`.
Environment: local SQLite, demo seed, `PAYPAL_MODE=mock`, `AGENT_MODE=scripted`.
Phase A evidence is preserved under `docs/evidence/F1-23/S01` ... `S12`.

## S01-S12 regression

| ID | Scenario | Catalog outcome | API expected | Actual | Status | Evidence |
|---|---|---|---|---|---|---|
| SEED | Seed and policy data validation | N/A | N/A | N/A | **PASS** | `docs/evidence/F1-23/phase-b/regression/SEED` |
| S01 | S01_partial_payment_now | PENDING_MERCHANT | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/phase-b/regression/S01` |
| S02 | S02_installments_request | PENDING_MERCHANT | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/phase-b/regression/S02` |
| S03 | S03_exceeds_discount | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S03` |
| S04 | S04_reasonable_discount | PENDING_MERCHANT | PENDING_MERCHANT | PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/phase-b/regression/S04` |
| S05 | S05_ambiguous_slow_business | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S05` |
| S06 | S06_ambiguous_partial_later | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S06` |
| S07 | S07_hostile_customer | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S07` |
| S08 | S08_injection_ignore_instructions | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S08` |
| S09 | S09_injection_system_override | CLARIFICATION | BLOCKED / `CLARIFICATION_REQUIRED` | BLOCKED / `CLARIFICATION_REQUIRED` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S09` |
| S10 | S10_invalid_discount_150 | INVALID_AGENT_OUTPUT | BLOCKED / `INVALID_AGENT_OUTPUT` | BLOCKED / `INVALID_AGENT_OUTPUT` | **PASS_WITH_OBSERVATION** | `docs/evidence/F1-23/phase-b/regression/S10` |
| S11 | S11_text_mismatch | BLOCKED | BLOCKED / `TEXT_NUMBER_MISMATCH` | BLOCKED / `TEXT_NUMBER_MISMATCH` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S11` |
| S12 | S12_hidden_characters | BLOCKED | BLOCKED / `MAX_DISCOUNT_PCT` | BLOCKED / `MAX_DISCOUNT_PCT` | **PASS** | `docs/evidence/F1-23/phase-b/regression/S12` |

## F1-20 / F1-11 platform probes

| Check | Status | Evidence |
|---|---|---|
| F1-20 startup fails closed when LLM_API_KEY is missing | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| F1-20 production guard rejects DEMO_MODE=true | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| health reports AGENT_MODE=llm | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| scenario override returns PENDING_MERCHANT | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| scripted intent is used instead of a live LLM call | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| proposal audit trail is persisted | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| no fallback audit is emitted for the scripted override | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| F1-11 Sandbox bootstrap rejects PAYPAL_MODE=mock | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| F1-11 Sandbox bootstrap rejects a non-Sandbox URL | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| F1-11 Sandbox bootstrap rejects a missing Sandbox buyer | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| .env.example documents LLM_PROVIDER | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| .env.example documents LLM_MODEL | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| .env.example documents LLM_API_KEY | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| .env.example documents PAYPAL_SANDBOX_BUYER_EMAIL | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| .env.example documents ALLOW_SANDBOX_PAYMENT_SHORTCUT | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| .env.example documents PUBLIC_BASE_URL | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| DEPLOY.md documents python -m app.seed.sandbox_bootstrap | **FAIL** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| DEPLOY.md documents PAYPAL_WEBHOOK_ID | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |
| DEPLOY.md documents PAYPAL_SANDBOX_BUYER_EMAIL | **PASS** | `docs/evidence/F1-23/phase-b/platform-summary.json` |

The failing deployment-guide check is **DEF-02** (the guide omits `python -m app.seed.sandbox_bootstrap`).

## UI smoke - `origin/feat/ui-final-integration`

UI commit: `5f88861aff56fe158c9b4a8cf7a99f7eb904b0bf`

| Check | Status | Evidence |
|---|---|---|
| npm ci succeeds | **PASS** | `docs/evidence/F1-23/phase-b/ui/ui-summary.json` |
| production build succeeds | **FAIL** | `docs/evidence/F1-23/phase-b/ui/ui-summary.json` |
| Vite dev server starts | **PASS** | `docs/evidence/F1-23/phase-b/ui/ui-summary.json` |
| landing page renders | **PASS** | `docs/evidence/F1-23/phase-b/ui/ui-summary.json` |
| dashboard renders invoices | **PASS** | `docs/evidence/F1-23/phase-b/ui/ui-summary.json` |
| screenshots captured | **PASS** | `docs/evidence/F1-23/phase-b/ui/ui-summary.json` |

The failing UI build check is **DEF-03** (`mockAuditCursor` is unused under TypeScript).

## DEF-01 review

| Field | Result |
|---|---|
| Phase B status | OPEN |
| Can additional evidence resolve it? | False |
| Requires application change? | True |
| Evidence | `docs/evidence/F1-23/phase-b/def-01/analysis.json` |

## Blocked items

| ID | Scope | Dependency | Affected validation | Status |
|---|---|---|---|---|
| BLK-B01 | PayPal Sandbox real | PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_WEBHOOK_ID, PAYPAL_MERCHANT_EMAIL, PAYPAL_SANDBOX_BUYER_EMAIL and a public HTTPS URL | Real payment, real webhook signature, real invoice lifecycle | **BLOCKED** |
| BLK-B02 | Live Gemini LLM | LLM_PROVIDER, LLM_MODEL and an authorized LLM_API_KEY | Live intent extraction, tone quality, real-LLM injection resistance | **BLOCKED** |
| BLK-B03 | UI integration | PR #22 / feat/ui-final-integration merged and deployed with the backend | Full browser E2E against the real backend; only preview/build smoke is possible | **BLOCKED** |
| BLK-B04 | Deployed backend | Public backend URL and deployment credentials | Deployed-environment E2E; only the UI preview is public | **BLOCKED** |
