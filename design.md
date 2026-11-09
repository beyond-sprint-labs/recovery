# DueGuide — Frontend Architecture & Design Specification (DESIGN.md)

> **Design Philosophy & Anti-Slop Declaration:**  
> This document establishes the strict visual, architectural, and behavioral guidelines for the DueGuide user interface. It adheres to **anti-slop principles**: eliminating generic AI templates, decorative gradients, fake marketing claims, and unearned animations. Every visual choice exists to serve financial clarity, audit transparency, and strict merchant control.

---

## 1. Design Read & Dials

```
ENERGY:   ■■□□□ (2/5) — Authoritative, high-density financial utility; zero marketing circus.
RHYTHM:   ■■■■□ (4/5) — Distinct functional dichotomy: dense compliance ledger vs. focused customer card.
MOTION:   ■□□□□ (1/5) — Purely state-driven: transactional cell flashes and synchronous PayPal step indicators.
```

- **Focal Points:**
  - **Merchant / Auditor View:** The live event stream in AG Grid Community, with visual dominance on guardrail blocks (`PROPOSAL_BLOCKED`).
  - **Customer View:** The single, pre-approved repayment schedule and binary `Accept` / `Decline` action triggers.
- **Typography:**
  - UI & Controls: System Sans (`-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Roboto`) for high legibility.
  - Financial Data & Ledger: Monospace (`ui-monospace`, `Consolas`, monospace) for currency values, hashes, and sequences.

---

## 2. Palette & Visual Identity (Crafted White Theme)

No arbitrary dark mode, no decorative background glow meshes, and no colored drop-shadows.

| Role | Token / Value | Intent / Rule |
|---|---|---|
| **Canvas** | `#FFFFFF` / `#F8FAFC` | Crisp, clean, daylight-readable enterprise background. |
| **Borders & Dividers** | `#E2E8F0` / `#CBD5E1` | Subtle structural division; no floating drop shadows. |
| **Primary Text** | `#0F172A` (Slate 900) | High-contrast readability (contrast ratio > 12:1). |
| **Secondary Text** | `#64748B` (Slate 500) | Contextual labels, timestamps, and metadata (contrast > 4.5:1). |
| **Primary Action** | `#2563EB` (Blue 600) | Merchant controls, active tab indicators, and primary triggers. |
| **Guardrail Interception** | `#DC2626` / `#FEE2E2` | Reserved **strictly** for `PROPOSAL_BLOCKED` and policy violations. |
| **PayPal Confirmed** | `#16A34A` / `#DCFCE7` | Confirmed settlement, active status, and passed policy checks. |
| **Pending / Review** | `#D97706` / `#FEF3C7` | Merchant awaiting action and non-blocking warnings. |

---

## 3. Parallel Architecture: Day 1 Mock-Driven Work

The frontend runs fully decoupled from the backend from Day 1 using exact contract mock data.

### 3.1 Local Contract Mocks (`ui/src/mocks/`)
All mock files are exact replicas of `contracts/examples/`:
- `invoices.json` & `invoice.json`
- `policy.json`
- `proposal_pending.json` (Scenario A: Standard valid alternatives)
- `proposal_blocked.json` (Scenario B: S03 Max discount limit violation)
- `proposal_text_mismatch.json` (Scenario C: Text-number sanitizer mismatch)
- `approve_response.json`
- `customer_proposal.json` (Single pre-approved alternative)
- `execute_response.json`
- `audit_events.seed.json` & `audit_events.stream.json`

### 3.2 Unified API Client (`ui/src/api/client.ts`)
- Single point of access exposing:
  - `getInvoices()`
  - `createProposal(invoiceId, scenario)`
  - `approve(proposalId, req)`
  - `getCustomerProposal(token)`
  - `respondAsCustomer(token, req)`
  - `reconcile(invoiceId)`
  - `getAuditEvents(afterSeq)`
- When `VITE_USE_MOCKS=true`, calls simulate realistic network latency (300–600 ms).
- **Zero-Rebuild Backend Toggle:** Switchable at build time via `.env` (`VITE_USE_MOCKS=false`) or dynamically in the browser via `?use_mocks=false` or `localStorage.setItem('USE_MOCKS', 'false')`.
- **Live Stream Simulation:** In mock mode, `getAuditEvents()` feeds a new event from `audit_events.stream.json` every ~2 seconds into AG Grid via `api.applyTransaction({ add })`.

---

## 4. Contract Specifications by Screen

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               Screen Priority                                  │
│  1. Live Audit Grid  ───>  2. Comparator  ───>  3. Customer View  ───> 4. Invoices│
│     (The 30s "Wow")       (Approval Flow)       (Binary Decision)      (Portfolio)│
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Screen 1: Live Audit & Compliance Trail (Priority #1 — AG Grid "Wow Factor")
- **Component:** `ui/src/pages/AuditPage.tsx`
- **Data Source:** `GET /audit-events?after_seq={lastSeq}`
- **AG Grid Community Constraints (DEC-07):**
  - **100% Community Edition (`ag-grid-community`, `ag-grid-react`). Zero enterprise watermarks.**
  - `getRowId = (params) => params.data.event_id` to prevent duplicate re-renders.
  - Sorted descending by `seq` so newest audit telemetry appears at the top.
  - Incremental transactional ingestion: `api.applyTransaction({ add: [newEvent], addIndex: 0 })`.
  - Cell flashing: `api.flashCells({ rowNodes: [newNode] })` upon receipt of every new event.
  - **Visual Alert Rule (`rowClassRules`):** Rows with `action === 'PROPOSAL_BLOCKED'` or `severity === 'CRITICAL'` render with an intense crimson left-border and highlight.
  - Columns derived directly from `AuditEvent`:
    - `seq` (number, pinned left)
    - `ts` (formatted timestamp)
    - `severity` (`INFO` / `WARNING` / `CRITICAL` badge)
    - `action` (action name in bold)
    - `state_from → state_to` (monospace transition)
    - `invoice_id` & `proposal_id`
    - `actor` (`SYSTEM:id` / `MERCHANT:id` / `PAYPAL:id`)
    - `paypal_called` (Explicit `YES` / `NO` badge)
    - `rule` (interception rule code, attempted vs limit)
    - `paypal_ref` (optional transaction reference)
    - `summary` (human-readable engine log)

---

### Screen 2: Repayment Comparator (Merchant Approval Flow)
- **Component:** `ui/src/pages/ProposalPage.tsx`
- **Principle:** Strict human-in-the-loop merchant approval. The AI assistant drafts alternatives; the merchant selects and pre-approves **exactly one**.
- **`POST /proposals/{id}/approve` Contract:**
  - **Request:** `{"alternative_type": "settlement_discount" | "down_payment_installments", "note": string | null}`
  - **Approval Rule:** Every alternative card has an explicit **"Approve This Option"** button. There is **no global approve button**.
  - **Policy Violation View (S03 Scenario):**
    - When scenario is set to `BLOCKED`, renders explicit guardrail banner:
      - Rule: `MAX_DISCOUNT_PCT` (Attempted 40% > Merchant Limit 15%)
      - Protection Notice: `PayPal API Protection: NOT CALLED (Zero External Risk)`
  - **Plan B UI:** Includes a quick action button labeled *"Simulate customer acceptance"* for accelerated judge demonstrations.
  - **Reconciliation:** Includes *"Refresh from PayPal (Reconcile)"* button triggering `reconcile()`.

---

### Screen 3: Customer Portal (Binary Acceptance View)
- **Component:** `ui/src/pages/CustomerPage.tsx`
- **Route:** `/customer/:token` (accessible via direct link or modal)
- **Contract:** `GET /customer/proposals/{token} → CustomerProposalView`
  - **Strict Information Privacy:** Displays **only** the pre-approved alternative (`type`, `terms`, `amount_due_now`, `installment_amount`, `total_paid`, `schedule`) and the final customer message.
  - **Never exposes internal metrics:** `alternatives[]`, `policy_check`, `present_value`, `merchant_difference_vs_balance`, or agent reasoning are strictly hidden.
- **Binary Decision Contract:** `POST /customer/proposals/{token}/respond` with `{"decision": "ACCEPT" | "DECLINE"}`:
  - **DECLINE:** Transitions `PENDING_CUSTOMER → DECLINED` (terminal, PayPal not called).
  - **ACCEPT:** Transitions `PENDING_CUSTOMER → ACCEPTED → EXECUTING`, displaying a 3-step synchronous progress indicator:
    1. *Create replacement draft invoice*
    2. *Cancel original overdue invoice*
    3. *Dispatch replacement PayPal invoice*
  - **Final Receipt:** Displays replacement PayPal invoice ID, original cancelled ID, first payment confirmation status, and return navigation.

---

### Screen 4: Overdue Invoices List (Portfolio Grid)
- **Component:** `ui/src/pages/InvoicesPage.tsx`
- **Contract:** `GET /invoices`
- **Grid Layout:** AG Grid Community table displaying overdue balances, due dates, customer names, PayPal links, and a direct action button: *"Resolve Alternative →"* navigating immediately to the Comparator.

---

## 5. Audit Transition Reference & State Machine

| # | Trigger | State Transition | Audit Action | PayPal Called? |
|---|---|---|---|---|
| 1 | `POST /proposals` | `DRAFTED → PENDING_MERCHANT` | `PROPOSAL_DRAFTED` | `false` |
| 1' | AI exceeds policy limits | `DRAFTED → BLOCKED` | `PROPOSAL_BLOCKED` (CRITICAL) | `false` |
| 2 | `approve` (Merchant) | `PENDING_MERCHANT → APPROVED` | `PROPOSAL_APPROVED` | `false` |
| 3 | Token generation | `APPROVED → PENDING_CUSTOMER` | `CUSTOMER_LINK_ISSUED` | `false` |
| 3' | `reject` (Merchant) | `PENDING_MERCHANT → REJECTED` | `PROPOSAL_REJECTED` | `false` |
| 4 | `respond` DECLINE | `PENDING_CUSTOMER → DECLINED` | `CUSTOMER_DECLINED` | `false` |
| 4' | Token expiration | `PENDING_CUSTOMER → EXPIRED` | `CUSTOMER_LINK_EXPIRED` | `false` |
| 5 | `respond` ACCEPT | `PENDING_CUSTOMER → ACCEPTED → EXECUTING` | `CUSTOMER_ACCEPTED`, `EXECUTION_STARTED` | `false` |
| 6 | PayPal execution steps | (State stays `EXECUTING`) | `PAYPAL_DRAFT_CREATED`, `PAYPAL_ORIGINAL_CANCELLED`, `PAYPAL_INVOICE_SENT` | **`true`** |
| 7 | Success | `EXECUTING → EXECUTED` | `EXECUTION_COMPLETED` | `true` |
| 7' | Rollback failure | `EXECUTING → FAILED` | `EXECUTION_FAILED` (CRITICAL) | `true` |
| 7'' | Post-cancel drop | `EXECUTING → NEEDS_RECONCILIATION` | `EXECUTION_NEEDS_RECONCILIATION` (CRITICAL) | `true` |
| 8 | Reconcile recovery | `NEEDS_RECONCILIATION → EXECUTED` | `RECONCILED` | `true` |
| 9 | Payment confirmation | `EXECUTED → PAID` | `PAYMENT_CONFIRMED` | `true` |

---

## 6. Anti-Slop Guardrails & Quality Locks

1. **Strict Decimal String Money (DEC-02):**
   - **`parseFloat` and `Number()` are strictly forbidden for currency storage and calculations.**
   - Money is transported and stored as strings with 2 decimal places (`"1000.00"`, `"300.00"`).
   - Display formatting (`$1,000.00`) is handled purely visually in AG Grid `valueFormatter`.
2. **Community Edition Only (DEC-07):**
   - No `ag-grid-enterprise` packages. Zero license banners or trial watermarks.
3. **Strict English Copy & Mandatory Legal Disclaimer:**
   - All buttons, tables, column headers, and statuses must be in strict English.
   - The regulatory notice must remain permanently visible at the bottom of the interface:
     > *"Simulation subject to merchant approval and customer acceptance. Not financial or legal advice."*
4. **Anti-Slop Craftsmanship Checks:**
   - **No decorative filler:** No meaningless icons, unattached badges, or fake counters.
   - **No AI marketing slop:** No *"Unlock AI synergy"* or *"Next-gen recovery algorithm"*; only concrete operational terms (*"Policy rule exceeded"*, *"Synchronous PayPal Orchestration"*, *"Schedule item #1"*).
   - **Keyboard & Screen Reader Accessible:** Real semantic HTML elements (`<button>`, `<span>`) used in cell renderers rather than unstyled text or raw strings.

---

## 7. Delivery Gate Report

- [x] **Hard Gate:** Zero unverified claims, zero float math for currency, zero enterprise license dependencies.
- [x] **Purpose Gate:** Every badge, color token, and button has a verified functional purpose.
- [x] **Liveliness:** Explicit dials declared (ENERGY 2, RHYTHM 4, MOTION 1). High-density compliance stream contrasted with focused customer portal.
- [x] **Production Verified:** Verified live on Vercel at [https://ui-neon-alpha.vercel.app](https://ui-neon-alpha.vercel.app).
