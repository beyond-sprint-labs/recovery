# DEC-27: POST /proposals/{id}/reconcile replaces retry-close

- **Status:** Closed
- **Phase:** 1

## Context

By the time a retry is needed the original invoice is already cancelled, so retrying a close makes no sense.

## Decision

`reconcile` resumes from the last persisted step: it only retries the send of the pending draft and cleans orphan drafts. It is also invoked lazily on `GET /proposals/{id}` when the proposal is EXECUTED.

## Consequences

Audit events from this path carry `source=RECONCILIATION`. `NEEDS_RECONCILIATION` can only move to EXECUTED or FAILED.
