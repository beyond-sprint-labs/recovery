"""ORM models shared across the application.

Customers and invoices (F1-08) and the audit trail (F1-16) share one ``Base``.
Proposal and webhook tables are added by their owners as additive declarations.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CustomerRow(Base):
    """Fictional demo customers; email stays server-side."""

    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)


class InvoiceRow(Base):
    """Merchant invoices; customer_id links to the recipient's email."""

    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    balance: Mapped[str] = mapped_column(String(32), nullable=False)
    due_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    paypal_invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditEventRow(Base):
    """Append-only audit trail.

    ``seq`` is the monotonic cursor used by incremental polling. ``sqlite_autoincrement``
    makes SQLite never reuse a value, even if rows are deleted. The public ``event_id`` is
    derived from ``seq`` by the repository, so it is not stored.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_proposal_id_seq", "proposal_id", "seq"),
        {"sqlite_autoincrement": True},
    )

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    rule: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    proposed_by: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    paypal_called: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    paypal_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
