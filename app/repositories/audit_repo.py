"""Data access for the audit trail. No business rules live here."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import AuditEventRow
from app.core.schemas import Actor, AuditEvent, RuleHit, Severity
from app.core.states import ProposalStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEntry:
    """Everything needed to append one audit event."""

    ts: datetime
    actor: Actor
    action: str
    severity: Severity
    summary: str
    invoice_id: str | None = None
    proposal_id: str | None = None
    state_from: ProposalStatus | None = None
    state_to: ProposalStatus | None = None
    rule: RuleHit | None = None
    proposed_by: Actor | None = None
    paypal_called: bool = False
    source: str | None = None
    paypal_ref: str | None = None


def _to_schema(row: AuditEventRow) -> AuditEvent:
    # SQLite returns naive datetimes; everything we store is UTC.
    ts = row.ts if row.ts.tzinfo is not None else row.ts.replace(tzinfo=UTC)
    return AuditEvent(
        event_id=f"aud_{row.seq:06d}",
        seq=row.seq,
        ts=ts,
        actor=Actor(type=row.actor_type, id=row.actor_id, mode=row.actor_mode),
        action=row.action,
        invoice_id=row.invoice_id,
        proposal_id=row.proposal_id,
        state_from=ProposalStatus(row.state_from) if row.state_from else None,
        state_to=ProposalStatus(row.state_to) if row.state_to else None,
        severity=Severity(row.severity),
        rule=RuleHit.model_validate(row.rule) if row.rule else None,
        summary=row.summary,
        proposed_by=Actor.model_validate(row.proposed_by) if row.proposed_by else None,
        paypal_called=row.paypal_called,
        source=row.source,
        paypal_ref=row.paypal_ref,
    )


class AuditRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: AuditEntry) -> AuditEvent:
        """Insert one event and flush so ``seq`` is assigned. Never commits."""
        row = AuditEventRow(
            ts=entry.ts.astimezone(UTC),
            actor_type=entry.actor.type,
            actor_id=entry.actor.id,
            actor_mode=entry.actor.mode,
            action=entry.action,
            invoice_id=entry.invoice_id,
            proposal_id=entry.proposal_id,
            state_from=entry.state_from.value if entry.state_from else None,
            state_to=entry.state_to.value if entry.state_to else None,
            severity=entry.severity.value,
            rule=entry.rule.model_dump(mode="json") if entry.rule else None,
            summary=entry.summary,
            proposed_by=entry.proposed_by.model_dump(mode="json") if entry.proposed_by else None,
            paypal_called=entry.paypal_called,
            source=entry.source,
            paypal_ref=entry.paypal_ref,
        )
        self._session.add(row)
        self._session.flush()
        return _to_schema(row)

    def list_after(
        self, *, after_seq: int, limit: int, proposal_id: str | None = None
    ) -> list[AuditEvent]:
        """Events with ``seq > after_seq`` in ascending order."""
        stmt = select(AuditEventRow).where(AuditEventRow.seq > after_seq)
        if proposal_id is not None:
            stmt = stmt.where(AuditEventRow.proposal_id == proposal_id)
        stmt = stmt.order_by(AuditEventRow.seq.asc()).limit(limit)
        return [_to_schema(row) for row in self._session.scalars(stmt).all()]
