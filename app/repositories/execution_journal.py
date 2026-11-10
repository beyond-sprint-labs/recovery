"""SQLAlchemy implementation of the ``ExecutionJournal`` port (F1-18b).

Every call opens its OWN short session and commits (or rolls back) before returning, so no
database transaction is ever open while ``ExecutionService`` talks to PayPal (invariant 5).
One step = one transaction: the audit event, ``proposals.execution`` and, when the step moves
the state machine, the compare-and-set transition succeed or fail together.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

from sqlalchemy.orm import Session, sessionmaker

from app.core.schemas import Actor
from app.core.states import assert_transition
from app.repositories.audit_repo import AuditRepo
from app.repositories.proposals_repo import ExecutionRecord, ProposalsRepo
from app.services.audit_service import AuditService
from app.services.execution_service import ExecutionSnapshot, ExecutionStateError, StepRecord

EXECUTION_ACTOR: Final = Actor(type="SYSTEM", id="execution_service")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class SqlExecutionJournal:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def load(self, proposal_id: str) -> ExecutionSnapshot | None:
        with self._session_factory() as session:
            record = ProposalsRepo(session).get_execution(proposal_id)
        if record is None:
            return None
        return ExecutionSnapshot(
            request_id=record.request_id,
            draft_id=record.draft_id,
            original_cancelled=record.original_cancelled,
            new_sent=record.new_sent,
        )

    def record(self, step: StepRecord) -> None:
        now = self._clock()
        with self._session_factory() as session:
            try:
                self._write(session, step, now)
                session.commit()
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _write(session: Session, step: StepRecord, now: datetime) -> None:
        if (step.state_from is None) != (step.state_to is None):
            raise ExecutionStateError("state_from and state_to must be set together")
        if step.state_from is not None and step.state_to is not None:
            assert_transition(step.state_from, step.state_to)

        proposals = ProposalsRepo(session)
        invoice_id = proposals.get_invoice_id(step.proposal_id)
        if invoice_id is None:
            raise ExecutionStateError(f"Proposal {step.proposal_id} not found")

        persisted = proposals.save_execution_step(
            proposal_id=step.proposal_id,
            execution=ExecutionRecord(
                request_id=step.snapshot.request_id,
                draft_id=step.snapshot.draft_id,
                original_cancelled=step.snapshot.original_cancelled,
                new_sent=step.snapshot.new_sent,
            ),
            paypal_called=step.paypal_called,
            state_from=step.state_from,
            state_to=step.state_to,
            now=now,
        )
        if not persisted:
            raise ExecutionStateError(
                f"Proposal {step.proposal_id} is not in the state required by step "
                f"{step.action.value}"
            )

        AuditService(AuditRepo(session)).record(
            actor=EXECUTION_ACTOR,
            action=step.action.value,
            severity=step.severity,
            summary=step.summary,
            invoice_id=invoice_id,
            proposal_id=step.proposal_id,
            state_from=step.state_from,
            state_to=step.state_to,
            paypal_called=step.paypal_called,
            source=step.source,
            paypal_ref=step.paypal_ref,
        )
