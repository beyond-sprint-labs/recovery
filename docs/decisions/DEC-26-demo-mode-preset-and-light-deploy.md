# DEC-26: DEMO_MODE is a strict preset and the deployment stays light

- **Status:** Closed
- **Phase:** 1

## Context

SQLite under several writers produces `database is locked`, and a 1 GB VM without swap gets OOM-killed.

## Decision

`DEMO_MODE=true` fixes `PAYPAL_MODE=mock`, `AGENT_MODE=scripted`, SQLite and seed data. Production refuses to boot with a mock PayPal or a scripted agent. The deployment is one VM, one Uvicorn worker, 2 GB swap and SQLite in WAL mode.

## Consequences

Judges can run the project without keys (AC9). The deployed instance uses the real PayPal Sandbox. PostgreSQL is used only when memory allows it.
