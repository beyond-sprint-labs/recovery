# DEC-15: Replacement sequence: preflight, draft, cancel original, send

- **Status:** Confirmed in F1-03
- **Phase:** 1

## Context

Two payable invoices for one debt would let a customer pay twice (AC11).

## Decision

Preflight checks the original is cancellable and unpaid, then: create the replacement as DRAFT (not payable), cancel the original, send the draft. Each step is persisted before the next one and no DB transaction stays open during a PayPal call.

## Consequences

Create fails: FAILED. Cancel fails: delete the draft, then FAILED. Send fails after cancel: NEEDS_RECONCILIATION, and reconcile only retries the send because a cancellation is not reversible. PayPal has no idempotent create (422 DUPLICATE_INVOICE_NUMBER), so we derive a deterministic invoice number per proposal and persist `draft_id` first.
