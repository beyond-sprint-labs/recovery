# F1-08: deterministic demo seed data

`app/seed/customers.json` and `app/seed/invoices.json` are JSON arrays. They contain
fictional customers and USD invoices for local integration tests and E2E setup.
Customer IDs link the files. Money uses strings with exactly two decimal places;
dates use ISO `YYYY-MM-DD`; unknown fields, invalid emails, duplicate IDs and
broken customer references are rejected before insertion.

## Load a local database

Install the project with Python 3.12 or 3.13 using `pip install -e ".[dev]"`, then run:

```bash
python -m app.seed.loader
```

The command uses `DATABASE_URL` from the existing settings (`.env` or environment),
creates missing tables and commits all inserts in one transaction. It refuses
`APP_ENV=production`. It prints inserted counts and makes no network requests.
Running it again inserts only missing IDs; existing invoice balances, statuses and
PayPal references are preserved. A conflicting existing customer identity aborts
the transaction. Startup does not automatically seed a database.

Tests can call `load_seed_data()` for validated fixtures or
`seed_database(session)` inside a transaction owned by the test/service. Do not
swallow loading errors and commit a partially loaded transaction.

## Fixture cases

| Invoice | Balance | Status | Purpose |
| --- | --- | --- | --- |
| INV-001 | 1000.00 | OVERDUE | Canonical S01–S12 scenario input and finance golden case |
| INV-002 | 250.50 | OVERDUE | Smaller balance with cents |
| INV-003 | 1500.00 | OVERDUE | Larger balance, month-end due date |
| INV-004 | 0.00 | PAID | Negative lifecycle test: already paid |
| INV-005 | 400.00 | CANCELLED | Negative lifecycle test: cancelled |

The original scenario IDs and `tests/scenarios/scenarios.json` are unchanged. Use
an explicit test clock for deterministic proposal dates; invoice due dates are
fixed fixtures, not a request to modify the finance engine's calculation date.

## Email and PayPal integration

Emails use `example.com`: syntactically valid, fictional addresses, not deliverable
Sandbox buyers. Join `InvoiceRow.customer_id` to `CustomerRow.id`, then pass its
`email` as `NewInvoiceReq.recipient_email`. The public `Invoice` response schema
is unchanged and does not expose customer email.

All `paypal_invoice_id` values are null: these fixtures do not create invoices at
PayPal or populate MockPayPalGateway's separate in-memory store. Execution E2E
setup must create/send an original invoice through the selected gateway and store
the returned ID. For Sandbox delivery configure an actual test buyer through
`PAYPAL_SANDBOX_BUYER_EMAIL`, which the real gateway uses to override the seed email.
Never treat a fabricated seed ID as a real PayPal invoice.

## Coordination with F1-13

This proposal introduces CustomerRow and InvoiceRow on the shared Base because
main has no invoice persistence yet. InvoiceRow retains the fields proposed by
PR #10 and adds nullable customer_id for compatibility with its existing fixtures.
When integrating #10, reuse this InvoiceRow declaration and add ProposalRow to the
same module; do not declare a second `invoices` table. Existing databases created
from #10 need a schema migration for customer_id; create_all does not alter tables.
Use a fresh isolated demo database when evaluating this proposal against main.

This task supplies data and persistence setup. Invoice HTTP endpoints, proposal
lifecycle behavior and execution remain the responsibility of their service tasks.
