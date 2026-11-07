"""Validate all bundled F1-08 data before inserting any rows. No PayPal calls."""

import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    StringConstraints,
    TypeAdapter,
)
from sqlalchemy.orm import Session

from app.core.models import CustomerRow, InvoiceRow
from app.core.schemas import Invoice, InvoiceStatus

DATA_DIR = Path(__file__).parent
RESERVED_EMAIL_DOMAINS = frozenset({"example.com", "example.org"})
_SEED_ID_RE = re.compile(r"[A-Z]{3}-[0-9]{3,9}")


def _require_ascii_seed_id(value: str) -> str:
    """Fail closed: only ASCII ``AAA-000`` ids, never Unicode lookalikes or whitespace."""
    if _SEED_ID_RE.fullmatch(value) is None:
        raise ValueError("Seed ids must match AAA-000 using ASCII A-Z and 0-9 only")
    return value


def _require_clean_name(value: str) -> str:
    """Reject non-NFKC text, irregular whitespace and any control/format/unassigned char."""
    if unicodedata.normalize("NFKC", value) != value:
        raise ValueError("Name must be NFKC-normalized")
    if " ".join(value.split()) != value:
        raise ValueError("Name must not have leading, trailing or repeated whitespace")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("Name must not contain control, format or unassigned characters")
    return value


def _require_reserved_email(value: str) -> str:
    """Seed recipients must be ASCII addresses on reserved fictional domains (exact match)."""
    _, _, domain = value.rpartition("@")
    if not value.isascii() or domain.lower() not in RESERVED_EMAIL_DOMAINS:
        raise ValueError("Seed emails must be ASCII addresses at example.com or example.org")
    return value


SeedId = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=64),
    AfterValidator(_require_ascii_seed_id),
]
Name = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=255),
    AfterValidator(_require_clean_name),
]
SeedEmail = Annotated[EmailStr, AfterValidator(_require_reserved_email)]


class SeedCustomer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: SeedId
    name: Name
    email: SeedEmail


class SeedInvoice(Invoice):
    model_config = ConfigDict(extra="forbid")

    id: SeedId
    customer_id: SeedId
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
        if invoice.paypal_invoice_id is not None:
            raise ValueError(f"Seed invoice {invoice.id} must not carry a PayPal id")
        if invoice.status == InvoiceStatus.PAID and Decimal(invoice.balance) != 0:
            raise ValueError(f"PAID invoice {invoice.id} must have zero balance")
        if invoice.status == InvoiceStatus.OVERDUE and Decimal(invoice.balance) <= 0:
            raise ValueError(f"OVERDUE invoice {invoice.id} must have positive balance")
    return SeedData(tuple(customers), tuple(invoices))


def seed_database(session: Session, data_dir: Path = DATA_DIR) -> dict[str, int]:
    """Insert missing IDs only; caller owns commit/rollback. Never reset existing data.

    Identity fields of existing rows must match the seed. Runtime state (balance, status,
    PayPal reference) is deliberately left untouched.
    """
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
        existing_invoice = session.get(InvoiceRow, invoice.id)
        if existing_invoice is None:
            session.add(InvoiceRow(**invoice.model_dump(mode="json")))
            counts["invoices_inserted"] += 1
        elif (
            existing_invoice.customer_id != invoice.customer_id
            or existing_invoice.customer_name != invoice.customer_name
            or existing_invoice.currency != invoice.currency
            or existing_invoice.due_date != invoice.due_date.isoformat()
        ):
            raise ValueError(f"Existing invoice {invoice.id} conflicts with seed identity")
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
