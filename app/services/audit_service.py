"""Audit service: the only writer of audit events (AC8).

``record`` flushes but never commits: the caller owns the transaction, so an event is
persisted atomically with the state transition it describes.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final, Literal

from app.core.errors import UnprocessableError
from app.core.schemas import Actor, AuditEvent, AuditEventsPage, RuleHit, Severity
from app.core.states import ProposalStatus
from app.repositories.audit_repo import AuditEntry, AuditRepo

SUMMARY_MAX_LENGTH: Final = 500
MAX_PAGE_LIMIT: Final = 500

AuditSource = Literal["API", "UI", "WEBHOOK", "RECONCILIATION"]


def _utc_now() -> datetime:
    """Current UTC time truncated to seconds (contract: YYYY-MM-DDTHH:MM:SSZ)."""
    return datetime.now(UTC).replace(microsecond=0)


class AuditService:
    def __init__(self, repo: AuditRepo, clock: Callable[[], datetime] = _utc_now) -> None:
        self._repo = repo
        self._clock = clock

    def record(
        self,
        *,
        actor: Actor,
        action: str,
        severity: Severity,
        summary: str,
        invoice_id: str | None = None,
        proposal_id: str | None = None,
        state_from: ProposalStatus | None = None,
        state_to: ProposalStatus | None = None,
        rule: RuleHit | None = None,
        proposed_by: Actor | None = None,
        paypal_called: bool = False,
        source: AuditSource | None = None,
        paypal_ref: str | None = None,
    ) -> AuditEvent:
        """Append one event inside the caller's transaction (no commit)."""
        entry = AuditEntry(
            ts=self._clock(),
            actor=actor,
            action=action,
            severity=severity,
            summary=summary[:SUMMARY_MAX_LENGTH],
            invoice_id=invoice_id,
            proposal_id=proposal_id,
            state_from=state_from,
            state_to=state_to,
            rule=rule,
            proposed_by=proposed_by,
            paypal_called=paypal_called,
            source=source,
            paypal_ref=paypal_ref,
        )
        return self._repo.add(entry)

    def list_events(
        self, *, after_seq: int, limit: int, proposal_id: str | None
    ) -> AuditEventsPage:
        """Incremental page. ``next_seq`` keeps the cursor when nothing new arrived."""
        if after_seq < 0 or not 1 <= limit <= MAX_PAGE_LIMIT:
            raise UnprocessableError(
                "INVALID_PAGINATION",
                f"after_seq must be >= 0 and limit must be between 1 and {MAX_PAGE_LIMIT}",
            )
        items = self._repo.list_after(after_seq=after_seq, limit=limit, proposal_id=proposal_id)
        next_seq = items[-1].seq if items else after_seq
        return AuditEventsPage(items=items, next_seq=next_seq)
