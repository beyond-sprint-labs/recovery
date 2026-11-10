# Integration tests

End-to-end checks that drive the FastAPI app through its public HTTP contract
(`/api/v1`, Section 4 of the roadmap) on top of an isolated SQLite database. Every test gets a
fresh database from the autouse fixture in `tests/conftest.py`, so no test touches
`recovery.db`. Nothing here calls the real PayPal Sandbox or an LLM.

## Run from the terminal

```bash
pytest tests/integration                         # whole folder
pytest tests/integration/test_flow_demo.py       # full simulated demo flow (F1-12)
pytest "tests/integration/test_flow_demo.py::test_seeded_app_boots_with_demo_data"
pytest                                           # full suite, including unit tests
ruff check . && ruff format --check .            # lint, as in CI
```

## Run from the IDE test panel

- **VS Code:** install the Python extension, select the project's virtualenv, and enable
  pytest in your local (uncommitted) workspace settings: `"python.testing.pytestEnabled": true`.
  Open the Testing view; discovery uses `testpaths = ["tests"]` from `pyproject.toml`.
- **PyCharm:** set the default test runner to pytest (Settings > Tools > Python Integrated
  Tools), keep the working directory at the repository root, then run the `tests/integration`
  folder from the Project view.

## `test_flow_demo.py` (F1-12)

Runs the complete simulated demo flow through the public HTTP API:

1. **Bootstrapping:** Seeded overdue invoices are opened in the simulated PayPal gateway at startup (`DEMO_MODE=true`).
2. **Proposal Lifecycle:**
   - Invoices query (`GET /invoices`) and merchant policy inspection (`GET /policy`).
   - Proposal creation with input sanitization and deterministic script extraction (S01).
   - Hard policy gate: out-of-policy requests (S03: 40% discount) transition immediately to `BLOCKED` (HTTP 200).
   - Idempotency guarantees: mandatory `Idempotency-Key` prevents duplicate proposal generation.
3. **Merchant & Customer Flow:**
   - Merchant approval (`POST /proposals/{id}/approve`) emits single-use link with SHA-256 token hashing.
   - Customer binary view (`GET /customer/proposals/{token}`) and decision (`POST /customer/proposals/{token}/respond`).
   - Double-acceptance prevention: idempotent CAS guarantees single PayPal execution.
4. **Execution & Webhook:** Simulated atomic replacement (*draft -> cancel original -> send*) and verified payment confirmation moving proposal to `PAID`.

All steps are active and fully verified. The happy path reads its scenario parameters from `tests/scenarios/scenarios.json` (`S01`).

## Other integration tests

- `test_sqlite_concurrency.py` (F1-16): One writer plus five polling readers over SQLite WAL for 30s.
- `test_no_double_charge.py` (F1-18a): Verification of the atomic PayPal replacement sequence and rollback.
- `test_f1_18b_flows.py` (F1-18b): Reconcile, orphan draft cleanup, sandbox shortcut, and Invariant 5 verification.
- `test_webhook_flow.py` (F1-19): End-to-end PayPal webhook receipt, official signature verification, and idempotency.