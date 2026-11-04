# DEC-09: No Redis in Phase 1: idempotency lives in the database

- **Status:** Closed
- **Phase:** 1

## Context

The target host has 1 GB of RAM and Redis would add a daemon without adding guarantees we need.

## Decision

Webhook idempotency uses `webhook_events.event_id` as PRIMARY KEY, and proposal creation uses a UNIQUE `idempotency_key`. State changes are compare-and-set `UPDATE ... WHERE id=? AND status=?`.

## Consequences

Same ACID guarantee with one less service. A 0-row update maps to HTTP 409. Redis stays in the Phase 3 backlog.
