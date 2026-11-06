"""Validate all bundled F1-08 data before inserting any rows. No PayPal calls."""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, TypeAdapter
from sqlalchemy.orm import Session

from app.core.models import CustomerRow, InvoiceRow
from app.core.schemas import Invoice, InvoiceStatus

DATA_DIR = Path(__file__).parent
Identifier = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64)]
Name = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=255)]


class SeedCustomer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Identifier
    name: Name
    email: EmailStr


class SeedInvoice(Invoice):
    model_config = ConfigDict(extra="forbid")

    id: Identifier
    customer_id: Identifier
    customer_name: Name


@dataclass(frozen=True)
class SeedData:
    customers: tuple[SeedCustomer, ...]
    invoices: tuple[SeedInvoice, ...]


def _unique_ids(records: list[SeedCustomer] | list[SeedInvoice], label: str) -> None:
    ids = [row.id for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate {label} id")


def load_seed_data(data_dir: Path = DATA_DIR) -> SeedData:
    """Read strict JSON arrays, validate contracts and resolve customer references."""
    customers = TypeAdapter(list[SeedCustomer]).validate_json(
        (data_dir / "customers.json").read_text(encoding="utf-8")
    )
    invoices = TypeAdapter(list[SeedInvoice]).validate_json(
        (data_dir / "invoices.json").read_text(encoding="utf-8")
    )
    if not customers or not invoices:
        raise ValueError("Seed customers and invoices must not be empty")
    _unique_ids(customers, "customer")
    _unique_ids(invoices, "invoice")
    by_id = {customer.id: customer for customer in customers}
    for invoice in invoices:
        customer = by_id.get(invoice.customer_id)
        if customer is None:
            raise ValueError(f"Unknown customer_id for {invoice.id}")
        if invoice.customer_name != customer.name:
            raise ValueError(f"Customer name mismatch for {invoice.id}")
        if invoice.status == InvoiceStatus.PAID and Decimal(invoice.balance) != 0:
            raise ValueError(f"PAID invoice {invoice.id} must have zero balance")
        if invoice.status == InvoiceStatus.OVERDUE and Decimal(invoice.balance) <= 0:
            raise ValueError(f"OVERDUE invoice {invoice.id} must have positive balance")
    return SeedData(tuple(customers), tuple(invoices))


def seed_database(session: Session, data_dir: Path = DATA_DIR) -> dict[str, int]:
    """Insert missing IDs only; caller owns commit/rollback. Never reset existing data."""
    data = load_seed_data(data_dir)
    counts = {"customers_inserted": 0, "invoices_inserted": 0}
    for customer in data.customers:
        existing = session.get(CustomerRow, customer.id)
        if existing is None:
            session.add(CustomerRow(**customer.model_dump(mode="json")))
            counts["customers_inserted"] += 1
        elif existing.name != customer.name or existing.email != str(customer.email):
            raise ValueError(f"Existing customer {customer.id} conflicts with seed identity")
    session.flush()
    for invoice in data.invoices:
        if session.get(InvoiceRow, invoice.id) is None:
            session.add(InvoiceRow(**invoice.model_dump(mode="json")))
            counts["invoices_inserted"] += 1
    session.flush()
    return counts


def main() -> None:
    """Explicit local/demo database initialization: python -m app.seed.loader."""
    from app.core.config import get_settings
    from app.core.db import Base, get_engine, get_session_factory

    if get_settings().app_env == "production":
        raise SystemExit("Demo seed loading is unavailable in production")
    load_seed_data()  # Validate before creating tables.
    Base.metadata.create_all(get_engine())
    with get_session_factory().begin() as session:
        counts = seed_database(session)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
