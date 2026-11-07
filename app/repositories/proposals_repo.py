"""Data access for proposals. No business rules live here.

Writes flush but never commit: the service owns the transaction boundaries. Reads use
``populate_existing`` so a row held in the identity map is never served stale after the
compare-and-set finalization (which updates the database directly).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models import InvoiceRow, ProposalRow
from app.core.schemas import (
    Alternative,
    AttemptedAlternative,
    CustomerIntent,
    PolicyCheck,
    RuleHit,
    TextNumberCheck,
)
from app.core.states import ProposalStatus


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
class ProposalRecord:
    proposal_id: str
    invoice_id: str
    status: ProposalStatus
    idempotency_key: str
    request_hash: str
    engine_version: str
    currency: str
    result: ProposalResult | None  # None while the proposal is still DRAFTED
    execution: dict[str, object] = None


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
        execution=row.execution or {},
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

    def update_status(
        self,
        *,
        proposal_id: str,
        expected_status: ProposalStatus,
        new_status: ProposalStatus,
    ) -> bool:
        """State compare-and-set. Returns True if the transition was applied."""
        stmt = (
            update(ProposalRow)
            .where(
                ProposalRow.id == proposal_id,
                ProposalRow.status == expected_status.value,
            )
            .values(
                status=new_status.value,
                updated_at=datetime.now(UTC),
            )
        )
        outcome = cast("CursorResult[Any]", self._session.execute(stmt))
        return outcome.rowcount == 1

    def set_customer_token(self, proposal_id: str, token_hash: str, expires_at: datetime) -> None:
        """Store the token hash and the expiration date (without storing the token in plaintext)."""
        stmt = (
            update(ProposalRow)
            .where(ProposalRow.id == proposal_id)
            .values(
                customer_token_hash=token_hash,
                customer_token_expires_at=expires_at,
                updated_at=datetime.now(UTC),
            )
        )
        self._session.execute(stmt)

    def consume_customer_token(self, proposal_id: str) -> bool:
        """Marks the token as used. Returns True if it was successfully consumed."""
        stmt = (
            update(ProposalRow)
            .where(
                ProposalRow.id == proposal_id,
                ProposalRow.customer_token_used_at.is_(None),
            )
            .values(customer_token_used_at=datetime.now(UTC))
        )
        outcome = cast("CursorResult[Any]", self._session.execute(stmt))
        return outcome.rowcount == 1

    def get_invoice_for_proposal(self, proposal_id: str) -> InvoiceRow | None:
        """Retrieves the invoice associated with a proposal (for the ExecutionService)."""
        proposal = self._session.get(ProposalRow, proposal_id)
        if proposal is None:
            return None
        return self._session.get(InvoiceRow, proposal.invoice_id)
