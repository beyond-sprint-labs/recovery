"""Data access for proposals. No business rules live here.

Writes flush but never commit: the service owns the transaction boundaries. Reads use
``populate_existing`` so a row held in the identity map is never served stale after the
compare-and-set finalization (which updates the database directly).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Self, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models import ProposalRow
from app.core.schemas import (
    Alternative,
    AlternativeType,
    AttemptedAlternative,
    CustomerIntent,
    PolicyCheck,
    RuleHit,
    TextNumberCheck,
)
from app.core.states import ProposalStatus

# Statuses in which execution steps that do not change the state may be persisted.
EXECUTION_WRITABLE_STATUSES: Final = (
    ProposalStatus.EXECUTING.value,
    ProposalStatus.NEEDS_RECONCILIATION.value,
)


class ProposalInsertConflictError(Exception):
    """The insert violated a constraint (normally the UNIQUE idempotency key)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class NewProposal:
    proposal_id: str
    invoice_id: str
    idempotency_key: str
    request_hash: str
    customer_message: str
    engine_version: str
    currency: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ProposalResult:
    """Everything the drafting pipeline persists when it leaves ``DRAFTED``."""

    customer_intent: CustomerIntent
    alternatives: list[Alternative]
    attempted: list[AttemptedAlternative]
    blocked_reasons: list[RuleHit]
    explanation: str | None
    customer_message_draft: str | None
    policy_check: PolicyCheck
    text_number_check: TextNumberCheck
    paypal_called: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionRecord:
    """Mirror of ``proposals.execution`` (ROADMAP 4.5): the PayPal replacement progress."""

    request_id: str
    draft_id: str | None = None
    original_cancelled: bool = False
    new_sent: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "draft_id": self.draft_id,
            "original_cancelled": self.original_cancelled,
            "new_sent": self.new_sent,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self:
        if "request_id" not in data:
            raise ValueError("proposals.execution is missing 'request_id'")
        draft_id = data.get("draft_id")
        return cls(
            request_id=str(data["request_id"]),
            draft_id=str(draft_id) if draft_id is not None else None,
            original_cancelled=bool(data.get("original_cancelled", False)),
            new_sent=bool(data.get("new_sent", False)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ProposalRecord:
    proposal_id: str
    invoice_id: str
    status: ProposalStatus
    idempotency_key: str
    request_hash: str
    engine_version: str
    currency: str
    result: ProposalResult | None  # None while the proposal is still DRAFTED
    approved_alternative: AlternativeType | None = None
    execution: ExecutionRecord | None = None
    last_paypal_check_at: datetime | None = None


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything we store is UTC."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _to_record(row: ProposalRow) -> ProposalRecord:
    result: ProposalResult | None = None
    if row.customer_intent is not None:
        result = ProposalResult(
            customer_intent=CustomerIntent.model_validate(row.customer_intent),
            alternatives=[Alternative.model_validate(item) for item in row.alternatives or []],
            attempted=[AttemptedAlternative.model_validate(item) for item in row.attempted or []],
            blocked_reasons=[RuleHit.model_validate(item) for item in row.blocked_reasons or []],
            explanation=row.explanation,
            customer_message_draft=row.customer_message_draft,
            policy_check=PolicyCheck.model_validate(row.policy_check),
            text_number_check=TextNumberCheck.model_validate(row.text_number_check),
            paypal_called=row.paypal_called,
        )
    return ProposalRecord(
        proposal_id=row.id,
        invoice_id=row.invoice_id,
        status=ProposalStatus(row.status),
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        engine_version=row.engine_version,
        currency=row.currency,
        result=result,
        approved_alternative=(
            AlternativeType(row.approved_alternative) if row.approved_alternative else None
        ),
        execution=ExecutionRecord.from_json(row.execution) if row.execution else None,
        last_paypal_check_at=_as_utc(row.last_paypal_check_at),
    )


class ProposalsRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_drafted(self, new: NewProposal) -> None:
        """Insert a ``DRAFTED`` row and flush. Raises on a constraint violation."""
        created = new.created_at.astimezone(UTC)
        row = ProposalRow(
            id=new.proposal_id,
            invoice_id=new.invoice_id,
            status=ProposalStatus.DRAFTED.value,
            idempotency_key=new.idempotency_key,
            request_hash=new.request_hash,
            customer_message=new.customer_message,
            engine_version=new.engine_version,
            currency=new.currency,
            paypal_called=False,
            created_at=created,
            updated_at=created,
        )
        try:
            self._session.add(row)
            self._session.flush()
        except IntegrityError as exc:
            raise ProposalInsertConflictError("proposal insert violated a constraint") from exc

    def get(self, proposal_id: str) -> ProposalRecord | None:
        stmt = (
            select(ProposalRow)
            .where(ProposalRow.id == proposal_id)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(stmt).one_or_none()
        return _to_record(row) if row is not None else None

    def get_by_idempotency_key(self, idempotency_key: str) -> ProposalRecord | None:
        stmt = (
            select(ProposalRow)
            .where(ProposalRow.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(stmt).one_or_none()
        return _to_record(row) if row is not None else None

    def find_by_draft_id(self, draft_id: str) -> ProposalRecord | None:
        """Proposal whose replacement invoice has this PayPal id (webhook correlation, F1-19).

        Matches ``proposals.execution.draft_id`` only, so events of the ORIGINAL invoice never
        correlate. ``as_string()`` compiles to ``json_extract`` on SQLite and ``->>`` on
        PostgreSQL. There is no index: the table is tiny in Phase 1.
        """
        stmt = (
            select(ProposalRow)
            .where(ProposalRow.execution["draft_id"].as_string() == draft_id)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(stmt).first()
        return _to_record(row) if row is not None else None

    def get_invoice_id(self, proposal_id: str) -> str | None:
        stmt = select(ProposalRow.invoice_id).where(ProposalRow.id == proposal_id)
        return self._session.scalars(stmt).one_or_none()

    def get_execution(self, proposal_id: str) -> ExecutionRecord | None:
        stmt = select(ProposalRow.execution).where(ProposalRow.id == proposal_id)
        data = self._session.scalars(stmt).one_or_none()
        return ExecutionRecord.from_json(data) if data else None

    def finalize_drafted(
        self,
        *,
        proposal_id: str,
        status: ProposalStatus,
        result: ProposalResult,
        now: datetime,
    ) -> bool:
        """Compare-and-set ``DRAFTED -> status``. Returns False when no row matched."""
        stmt = (
            update(ProposalRow)
            .where(
                ProposalRow.id == proposal_id,
                ProposalRow.status == ProposalStatus.DRAFTED.value,
            )
            .values(
                status=status.value,
                customer_intent=result.customer_intent.model_dump(mode="json"),
                alternatives=[alt.model_dump(mode="json") for alt in result.alternatives],
                attempted=[item.model_dump(mode="json") for item in result.attempted],
                blocked_reasons=[hit.model_dump(mode="json") for hit in result.blocked_reasons],
                explanation=result.explanation,
                customer_message_draft=result.customer_message_draft,
                policy_check=result.policy_check.model_dump(mode="json"),
                text_number_check=result.text_number_check.model_dump(mode="json"),
                paypal_called=result.paypal_called,
                updated_at=now.astimezone(UTC),
            )
            .execution_options(synchronize_session=False)
        )
        outcome = cast("CursorResult[Any]", self._session.execute(stmt))
        return outcome.rowcount == 1

    def save_execution_step(
        self,
        *,
        proposal_id: str,
        execution: ExecutionRecord,
        paypal_called: bool,
        state_from: ProposalStatus | None,
        state_to: ProposalStatus | None,
        now: datetime,
    ) -> bool:
        """Persist one execution step; compare-and-set when it moves the state machine.

        With ``state_to`` the row must currently be in ``state_from``. Without it the row must
        be EXECUTING or NEEDS_RECONCILIATION. Returns False when no row matched.
        """
        values: dict[str, Any] = {
            "execution": execution.to_json(),
            "updated_at": now.astimezone(UTC),
        }
        if paypal_called:
            values["paypal_called"] = True
        if state_to is not None:
            if state_from is None:
                raise ValueError("state_from is required when state_to is set")
            values["status"] = state_to.value
            guard = ProposalRow.status == state_from.value
        else:
            guard = ProposalRow.status.in_(EXECUTION_WRITABLE_STATUSES)
        stmt = (
            update(ProposalRow)
            .where(ProposalRow.id == proposal_id, guard)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        outcome = cast("CursorResult[Any]", self._session.execute(stmt))
        return outcome.rowcount == 1

    def mark_paid(self, *, proposal_id: str, now: datetime) -> bool:
        """Compare-and-set ``EXECUTED -> PAID``. False when the webhook or another check won."""
        moment = now.astimezone(UTC)
        stmt = (
            update(ProposalRow)
            .where(
                ProposalRow.id == proposal_id,
                ProposalRow.status == ProposalStatus.EXECUTED.value,
            )
            .values(
                status=ProposalStatus.PAID.value,
                last_paypal_check_at=moment,
                updated_at=moment,
            )
            .execution_options(synchronize_session=False)
        )
        outcome = cast("CursorResult[Any]", self._session.execute(stmt))
        return outcome.rowcount == 1

    def touch_paypal_check(self, *, proposal_id: str, now: datetime) -> None:
        """Record that PayPal was asked, so lazy reconciliation is throttled."""
        stmt = (
            update(ProposalRow)
            .where(ProposalRow.id == proposal_id)
            .values(last_paypal_check_at=now.astimezone(UTC))
            .execution_options(synchronize_session=False)
        )
        self._session.execute(stmt)
