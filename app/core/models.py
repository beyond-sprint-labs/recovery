"""ORM models shared across the application.

Customers and invoices (F1-08), the audit trail (F1-16) and proposals (F1-13) share one
``Base``. Webhook tables are added by their owners as additive declarations.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
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
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    balance: Mapped[str] = mapped_column(String(32), nullable=False)
    due_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    paypal_invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProposalRow(Base):
    """Recovery proposals.

    The row is inserted as ``DRAFTED`` (committed before any agent call) so the UNIQUE
    ``idempotency_key`` protects concurrent requests. Result columns stay NULL until the
    compare-and-set finalization. Columns used by later slices (customer token, execution
    journal, reconciliation timestamp) are declared now because ``create_all`` never
    migrates an existing table.
    """

    __tablename__ = "proposals"
    __table_args__ = (Index("ix_proposals_invoice_id", "invoice_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_message: Mapped[str] = mapped_column(String(500), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Result of the drafting pipeline (NULL while DRAFTED).
    customer_intent: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    alternatives: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    attempted: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    blocked_reasons: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_message_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_check: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    text_number_check: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    paypal_called: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Later slices (approve / customer portal / execution / reconciliation).
    approved_alternative: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_message_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    customer_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    customer_token_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    last_paypal_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
