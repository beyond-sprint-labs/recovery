"""ORM models shared across the application.

Base is defined in app.core.db. All tables (audit_events, invoices, proposals,
webhook_events) must be declared here as additive declarations on the same Base.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UTCDateTime(TypeDecorator):
    """Ensures UTC timezone-aware datetimes when reading from SQLite.

    SQLite does not store timezone information. This TypeDecorator forces
    datetimes to be saved as UTC naive, and read back as UTC aware.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None:
            return value.replace(tzinfo=UTC)
        return value


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
    ts: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
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


class InvoiceRow(Base):
    """Merchant invoice record."""

    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    balance: Mapped[str] = mapped_column(String(32), nullable=False)  # Money string
    due_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # OVERDUE, PAID, CANCELLED
    paypal_invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProposalRow(Base):
    """Proposal lifecycle, audit data, and execution state."""

    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0.0")

    # Idempotency: one proposal per key
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    # Snapshots of the proposal calculation (JSON)
    customer_intent: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    policy_check: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    text_number_check: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    customer_message_draft: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    blocked_reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )

    # Approval & customer token
    approved_alternative: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    customer_token_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Execution state for F1-18 (JSON: draft_id, original_cancelled, new_sent, request_id)
    execution: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Meta
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_paypal_check_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
