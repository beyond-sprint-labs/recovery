# F1-08: deterministic demo seed data

`app/seed/customers.json` and `app/seed/invoices.json` are JSON arrays. They contain
fictional customers and USD invoices for local integration tests and E2E setup.
Customer IDs link the files. Everything is validated before any row is inserted:

- IDs use three ASCII uppercase letters, a hyphen and 3–9 ASCII digits
  (`[A-Z]{3}-[0-9]{3,9}`); lookalike or invisible Unicode is rejected.
- Names are NFKC-normalized, single-spaced and free of control or format characters.
- Emails are ASCII addresses on exactly `example.com` or `example.org`.
- Money uses strings with exactly two decimal places; dates use ISO `YYYY-MM-DD`.
- `paypal_invoice_id` must be `null`; unknown fields, duplicate IDs and broken customer
  references are rejected.

## Load a local database

Install the project with Python 3.12 or 3.13 using `pip install -e ".[dev]"`, then run:

```bash
python -m app.seed.loader
```

The command uses `DATABASE_URL` from the existing settings (`.env` or environment),
creates missing tables and commits all inserts in one transaction. It refuses
`APP_ENV=production`. It prints inserted counts and makes no network requests.
Running it again inserts only missing IDs; existing invoice balances, statuses and
PayPal references are preserved. A conflicting existing identity aborts the transaction: a customer with a different name or
email, or an invoice with a different customer, customer name, currency or due date.

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

Emails use the reserved `example.com` and `example.org` domains: syntactically valid, fictional
addresses, not deliverable Sandbox buyers. Join `InvoiceRow.customer_id` to `CustomerRow.id`, then pass its
`email` as `NewInvoiceReq.recipient_email`. The public `Invoice` response schema
is unchanged and does not expose customer email.

All `paypal_invoice_id` values are null: these fixtures do not create invoices at
PayPal or populate MockPayPalGateway's separate in-memory store. Execution E2E
setup must create/send an original invoice through the selected gateway and store
the returned ID. For Sandbox delivery configure an actual test buyer through
`PAYPAL_SANDBOX_BUYER_EMAIL`, which the real gateway uses to override the seed email.
Never treat a fabricated seed ID as a real PayPal invoice.

## Persistence and downstream tasks

This task owns `CustomerRow` and `InvoiceRow` on the shared `Base`. `InvoiceRow.customer_id`
is `NOT NULL` with a foreign key to `customers.id`, so every invoice resolves to a recipient
email. F1-13 adds `ProposalRow` to the same module and must not declare a second `invoices`
table. The public `Invoice` response is unchanged and never exposes `customer_id` or the email.

`tests/integration/test_flow_demo.py` documents the demo flow against the HTTP contract; its
pending steps are `xfail(strict=True)` until their cards land (see `tests/integration/README.md`).

This task supplies data and persistence setup. Invoice HTTP endpoints, proposal lifecycle
behavior and execution remain the responsibility of their service tasks.
