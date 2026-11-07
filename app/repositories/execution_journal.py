"""Real implementation of the ExecutionJournal port (F1-18b).

Each call to `record()` runs in its own short transaction: it inserts the audit event,
updates `proposals.execution` (the snapshot) and, when the transition is set, runs the
CAS transition on `proposals.status`. This guarantees invariant 5 (no DB transaction is
held open across a PayPal HTTP call).
"""

from sqlalchemy.orm import Session

from app.core.models import ProposalRow
from app.core.schemas import Actor
from app.repositories.audit_repo import AuditRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.services.audit_service import AuditService
from app.services.execution_service import (
    ExecutionJournal,
    ExecutionSnapshot,
    StepRecord,
)


class SqlAlchemyExecutionJournal(ExecutionJournal):
    def __init__(self, session: Session) -> None:
        self._session = session
        self._proposals = ProposalsRepo(session)
        self._audit = AuditService(AuditRepo(session))

    def load(self, proposal_id: str) -> ExecutionSnapshot | None:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return None
        raw = proposal.execution or {}
        return ExecutionSnapshot(
            request_id=raw.get("request_id", ""),
            draft_id=raw.get("draft_id"),
            original_cancelled=raw.get("original_cancelled", False),
            new_sent=raw.get("new_sent", False),
        )

    def record(self, step: StepRecord) -> None:
        """Atomically: audit event + execution snapshot update + optional CAS transition."""
        # 1. Update the execution JSON column on the proposal.
        row = self._session.get(ProposalRow, step.proposal_id)
        if row is None:
            raise RuntimeError(f"Proposal {step.proposal_id} not found")

        current_execution = dict(row.execution or {})
        current_execution.update(
            {
                "request_id": step.snapshot.request_id,
                "draft_id": step.snapshot.draft_id,
                "original_cancelled": step.snapshot.original_cancelled,
                "new_sent": step.snapshot.new_sent,
            }
        )
        row.execution = current_execution

        # 2. If this step moves the state machine, apply the CAS transition.
        if step.state_to is not None and step.state_from is not None:
            updated = self._proposals.update_status(
                proposal_id=step.proposal_id,
                expected_status=step.state_from,
                new_status=step.state_to,
            )
            if not updated:
                raise RuntimeError(
                    f"CAS failed for proposal {step.proposal_id}: "
                    f"expected {step.state_from.value}, got {row.status}"
                )

        # 3. Record the audit event.
        self._audit.record(
            actor=Actor(type="SYSTEM", id="execution_service"),
            action=step.action.value,
            severity=step.severity,
            summary=step.summary,
            proposal_id=step.proposal_id,
            state_from=step.state_from,
            state_to=step.state_to,
            source=step.source,
            paypal_ref=step.paypal_ref,
            paypal_called=step.paypal_called,
        )

        # 4. Commit this short transaction.
        self._session.commit()
