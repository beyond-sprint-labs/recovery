import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.db import Base, get_engine, get_session_factory
from app.core.models import CustomerRow, InvoiceRow
from app.core.schemas import Invoice
from app.finance import calculate_alternatives
from app.paypal.gateway import NewInvoiceReq
from app.seed.loader import DATA_DIR, load_seed_data, seed_database


def test_seed_invoice_drives_financial_golden_case():
    invoice = next(row for row in load_seed_data().invoices if row.id == "INV-001")
    result = calculate_alternatives(
        {
            "engine_version": "1.0.0",
            "invoice": {
                "id": invoice.id,
                "currency": invoice.currency,
                "balance": invoice.balance,
                "due_date": invoice.due_date.isoformat(),
                "as_of_date": "2026-11-01",
            },
            "alternatives": [
                {
                    "type": "down_payment_installments",
                    "down_payment_pct": "30",
                    "installments": 3,
                    "periodic_rate_pct": "1.5",
                }
            ],
            "policy": {
                "max_discount_pct": "15",
                "min_down_payment_pct": "20",
                "max_installments": 6,
                "max_financing_rate_pct": "2.0",
                "merchant_discount_rate_pct": "1.0",
            },
        }
    )
    alternative = result["alternatives"][0]
    assert alternative["amount_due_now"] == "300.00"
    assert [row["amount"] for row in alternative["schedule"]] == [
        "300.00",
        "240.37",
        "240.37",
        "240.36",
    ]
    assert alternative["total_paid"] == "1021.10"


def test_bundled_data_supports_contract_and_paypal_recipient():
    data = load_seed_data()
    customers = {row.id: row for row in data.customers}
    for row in data.invoices:
        Invoice.model_validate(row.model_dump(exclude={"customer_id"}))
        req = NewInvoiceReq(
            invoice_number=row.id,
            amount=row.balance,
            recipient_email=customers[row.customer_id].email,
        )
        assert req.recipient_email
    golden = next(row for row in data.invoices if row.id == "INV-001")
    assert golden.balance == "1000.00"
    assert golden.customer_name == "Northwind Demo LLC"
    assert golden.status == "OVERDUE"


def test_seed_persists_and_repeat_load_preserves_runtime_changes():
    Base.metadata.create_all(get_engine())
    factory = get_session_factory()
    with factory.begin() as session:
        assert seed_database(session) == {"customers_inserted": 3, "invoices_inserted": 5}
    with factory.begin() as session:
        row = session.get(InvoiceRow, "INV-001")
        assert row is not None
        row.balance = "0.00"
        row.status = "PAID"
    with factory.begin() as session:
        assert seed_database(session) == {"customers_inserted": 0, "invoices_inserted": 0}
    with factory() as session:
        row = session.get(InvoiceRow, "INV-001")
        assert row.balance == "0.00"
        assert row.status == "PAID"
        assert session.scalar(select(func.count()).select_from(CustomerRow)) == 3
        assert session.scalar(select(func.count()).select_from(InvoiceRow)) == 5


@pytest.mark.parametrize(
    ("file", "field", "value"),
    [
        ("customers", "email", "invalid-email"),
        ("customers", "unexpected", "field"),
        ("invoices", "balance", 1000.0),
        ("invoices", "balance", "1000.0"),
        ("invoices", "currency", "MXN"),
        ("invoices", "due_date", "2026-02-30"),
        ("invoices", "customer_id", "MISSING"),
        ("invoices", "customer_name", "Wrong name"),
        ("invoices", "status", "PAID"),
        ("invoices", "balance", "0.00"),
    ],
)
def test_invalid_seed_is_rejected_before_any_insert(tmp_path: Path, file, field, value):
    for name in ("customers", "invoices"):
        rows = json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
        if name == file:
            rows[0][field] = value
        (tmp_path / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as session:
        with pytest.raises((ValueError, ValidationError)):
            seed_database(session, tmp_path)
        assert session.scalar(select(func.count()).select_from(CustomerRow)) == 0
        assert session.scalar(select(func.count()).select_from(InvoiceRow)) == 0


@pytest.mark.parametrize("file", ["customers", "invoices"])
def test_duplicate_ids_are_rejected(tmp_path: Path, file):
    for name in ("customers", "invoices"):
        rows = json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
        if name == file:
            rows.append(rows[0])
        (tmp_path / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_seed_data(tmp_path)


def test_transaction_rolls_back_customer_identity_conflict():
    Base.metadata.create_all(get_engine())
    factory = get_session_factory()
    with factory.begin() as session:
        session.add(CustomerRow(id="CUS-002", name="Unrelated", email="other@example.com"))
    with pytest.raises(ValueError, match="conflicts"), factory.begin() as session:
        seed_database(session)
    with factory() as session:
        assert session.get(CustomerRow, "CUS-001") is None
        assert session.scalar(select(func.count()).select_from(InvoiceRow)) == 0
