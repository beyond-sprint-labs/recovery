# Integration tests

End-to-end checks that drive the FastAPI app through its public HTTP contract
(`/api/v1`, Section 4 of the roadmap) on top of an isolated SQLite database. Every test gets a
fresh database from the autouse fixture in `tests/conftest.py`, so no test touches
`recovery.db`. Nothing here calls the real PayPal Sandbox or an LLM.

## Run from the terminal

```bash
pytest tests/integration                         # whole folder
pytest tests/integration/test_flow_demo.py -rxX  # list XFAIL / XPASS(strict) outcomes
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

## `test_flow_demo.py`

Active tests (must pass today): the seeded app boots, the audit feed starts empty, and the
scenario catalog exposes `S03_exceeds_discount`.

Pending steps use `xfail(strict=True, raises=MissingDemoRoute)`. Only HTTP 404
from a requested demo endpoint is expected; assertion errors, HTTP 500 and other
failures remain real test failures. They fail until their card lands; when a step
starts passing, strict mode turns the unexpected pass into a CI failure. **The PR that implements
the step deletes the marker.** Never switch a marker to `strict=False`.

| Step | Unblocked by |
| --- | --- |
| `GET /invoices`, `GET /policy` | F1-13 |
| Blocked proposal (S03), blocked proposals cannot be approved | F1-13, F1-15 |
| Strict request body, mandatory `Idempotency-Key`, idempotent creation | F1-13 |
| Approve and one-alternative customer view | F1-13 |
| Double ACCEPT executes once, full audit trail | F1-12 (mock execution) |

The within-policy happy path reads its scenario id from `tests/scenarios/scenarios.json`
(the `S01` entry). If the catalog ids change, update the helper in the test module, not the
catalog.

## Other integration tests

- `test_sqlite_concurrency.py` (F1-16): one writer plus five pollers on SQLite WAL.
- `test_no_double_charge.py` (F1-18) and `test_webhook_idempotency.py` (F1-19) arrive with
  their cards.