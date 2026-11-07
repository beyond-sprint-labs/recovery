import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.db import Base, get_engine, get_session_factory
from app.core.models import CustomerRow, InvoiceRow
from app.seed.loader import DATA_DIR, load_seed_data, seed_database


def _write_variant(tmp_path: Path, file: str, field: str, value: object) -> None:
    for name in ("customers", "invoices"):
        rows = json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
        if name == file:
            rows[0][field] = value
        (tmp_path / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")


@pytest.mark.parametrize(
    ("file", "field", "value"),
    [
        ("customers", "id", "CUS-001\u200b"),
        ("customers", "id", "CUS\u2011001"),
        ("customers", "id", "cus-001"),
        ("customers", "id", "CUS-\uff10\uff10\uff11"),
        ("customers", "id", "CUS-001\n"),
        ("customers", "id", " CUS-001"),
        ("invoices", "id", "INV-001\u200b"),
        ("invoices", "id", "INV\u2011001"),
        ("invoices", "id", "inv-001"),
        ("invoices", "id", "INV-\uff10\uff10\uff11"),
        ("invoices", "id", "INV-001\n"),
        ("invoices", "customer_id", "CUS-001\u200b"),
        ("customers", "name", "Northwind\u200b Demo LLC"),
        ("customers", "name", "Northwind\u00a0Demo LLC"),
        ("customers", "name", "Northwind  Demo LLC"),
        ("customers", "name", " Northwind Demo LLC"),
        ("customers", "name", "   "),
        ("customers", "email", "buyer@gmail.com"),
        ("customers", "email", "buyer@sub.example.com"),
        ("customers", "email", "buyer@example.com.evil.com"),
        ("customers", "email", "\u00f1@example.com"),
        ("invoices", "paypal_invoice_id", "INV2-FAKE-0001"),
        ("invoices", "balance", "\u0661\u0660\u0660\u0660.\u0660\u0660"),
    ],
)
def test_adversarial_seed_values_fail_closed(tmp_path: Path, file, field, value):
    _write_variant(tmp_path, file, field, value)
    with pytest.raises(ValueError):
        load_seed_data(tmp_path)


@pytest.mark.parametrize("customer_id", [None, "CUS-999"])
def test_database_rejects_invoice_without_valid_customer(customer_id: str | None):
    Base.metadata.create_all(get_engine())
    with pytest.raises(IntegrityError), get_session_factory().begin() as session:
        session.add(
            InvoiceRow(
                id="INV-900",
                customer_id=customer_id,
                customer_name="Ghost Customer",
                currency="USD",
                balance="10.00",
                due_date="2026-10-15",
                status="OVERDUE",
                paypal_invoice_id=None,
            )
        )


@pytest.mark.parametrize(
    "override",
    [
        {"customer_id": "CUS-002"},
        {"due_date": "2026-10-16"},
        {"customer_name": "Renamed LLC"},
        {"currency": "EUR"},
    ],
)
def test_existing_invoice_identity_conflict_rolls_back(override: dict[str, object]):
    Base.metadata.create_all(get_engine())
    factory = get_session_factory()
    fields: dict[str, object] = {
        "id": "INV-001",
        "customer_id": "CUS-001",
        "customer_name": "Northwind Demo LLC",
        "currency": "USD",
        "balance": "1000.00",
        "due_date": "2026-10-15",
        "status": "OVERDUE",
        "paypal_invoice_id": None,
    }
    fields.update(override)
    with factory.begin() as session:
        session.add(
            CustomerRow(id="CUS-001", name="Northwind Demo LLC", email="northwind@example.com")
        )
        session.add(
            CustomerRow(id="CUS-002", name="Contoso Demo Studio", email="contoso@example.com")
        )
        session.flush()
        session.add(InvoiceRow(**fields))
    with pytest.raises(ValueError, match="conflicts"), factory.begin() as session:
        seed_database(session)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CustomerRow)) == 2
        assert session.scalar(select(func.count()).select_from(InvoiceRow)) == 1
        assert session.get(CustomerRow, "CUS-003") is None
