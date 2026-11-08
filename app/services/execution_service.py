"""Execution service: anti-double-charge replacement sequence (DEC-15 / AC11).

Pure orchestration (F1-18a). The service never opens or holds a database session: every
persisted step goes through ``ExecutionJournal``, whose implementation commits once per step,
so no database transaction is open while a PayPal HTTP request is in flight (invariant 5).

Sequence: preflight -> create draft -> cancel original -> send draft. A failed cancel rolls the
draft back only when PayPal confirms the original is still open. ``reconcile`` never cancels:
it sends the pending draft or, when the original is still open, discards the draft.
"""

from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final, Protocol

from app.core.schemas import Money, Severity
from app.core.states import ProposalStatus
from app.paypal.gateway import NewInvoiceReq, PayPalError, PayPalGateway, PayPalInvoiceState
from app.services.audit_service import AuditSource

CANCELLABLE_STATUSES: Final = frozenset({"SENT", "UNPAID"})  # confirmed against the F1-03 spike
DRAFT_STATUS: Final = "DRAFT"
SENT_STATUS: Final = "SENT"
CANCELLED_STATUS: Final = "CANCELLED"
PAID_STATUSES: Final = frozenset({"PAID", "MARKED_AS_PAID"})


class ExecutionAction(StrEnum):
    """Audit actions this service may emit (ROADMAP Section 4 transition table)."""

    DRAFT_CREATED = "PAYPAL_DRAFT_CREATED"
    ORIGINAL_CANCELLED = "PAYPAL_ORIGINAL_CANCELLED"
    INVOICE_SENT = "PAYPAL_INVOICE_SENT"
    DRAFT_DELETED = "PAYPAL_DRAFT_DELETED"
    COMPLETED = "EXECUTION_COMPLETED"
    FAILED = "EXECUTION_FAILED"
    NEEDS_RECONCILIATION = "EXECUTION_NEEDS_RECONCILIATION"
    RECONCILED = "RECONCILED"


class CancelOutcome(StrEnum):
    CANCELLED = "CANCELLED"
    STILL_OPEN = "STILL_OPEN"
    UNKNOWN = "UNKNOWN"


class ExecutionStateError(RuntimeError):
    """The persisted execution snapshot cannot support the requested operation."""


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Mirror of ``proposals.execution`` (ROADMAP 4.5)."""

    request_id: str
    draft_id: str | None = None
    original_cancelled: bool = False
    new_sent: bool = False


@dataclass(frozen=True)
class StepRecord:
    """One persisted step: its audit event, the execution snapshot after it and, when it moves
    the state machine, the transition. ``state_from``/``state_to`` are both set or both None."""

    proposal_id: str
    action: ExecutionAction
    severity: Severity
    summary: str
    snapshot: ExecutionSnapshot
    state_from: ProposalStatus | None = None
    state_to: ProposalStatus | None = None
    source: AuditSource | None = None
    paypal_ref: str | None = None
    paypal_called: bool = True


class ExecutionJournal(Protocol):
    """Persistence port. Every call runs in its OWN short transaction, committed (or rolled
    back) before it returns. The service never holds a session across a PayPal call."""

    def load(self, proposal_id: str) -> ExecutionSnapshot | None: ...

    def record(self, step: StepRecord) -> None:
        """Atomically: insert the audit event (actor SYSTEM/execution_service), update
        ``proposals.execution`` and, if ``state_to`` is set, run the CAS transition after
        ``assert_transition``. Errors propagate: the service never swallows them."""
        ...


@dataclass(frozen=True)
class ExecutionResult:
    status: ProposalStatus
    new_invoice_id: str | None
    original_invoice_id: str
    steps: tuple[str, ...]


@dataclass
class _Run:
    proposal_id: str
    original_invoice_id: str
    state_from: ProposalStatus
    snapshot: ExecutionSnapshot
    source: AuditSource | None = None
    steps: list[str] = field(default_factory=list)

    def result(self, status: ProposalStatus) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            new_invoice_id=self.snapshot.draft_id,
            original_invoice_id=self.original_invoice_id,
            steps=tuple(self.steps),
        )


def _has_payments(state: PayPalInvoiceState) -> bool:
    """Fail closed: an unparsable paid amount counts as a payment."""
    if state.paid_amount is None:
        return False
    try:
        return Decimal(state.paid_amount) > Decimal("0")
    except InvalidOperation:
        return True


def _is_cancellable(state: PayPalInvoiceState) -> bool:
    return state.status in CANCELLABLE_STATUSES and not _has_payments(state)


def is_paid_in_full(state: PayPalInvoiceState, expected_total: str) -> bool:
    """True only if PayPal reports a paid status AND the paid amount covers the expected total.

    Fail closed: a partial payment (PARTIALLY_PAID), a missing or unparsable paid amount, or any
    other status is NOT a confirmed payment (DEC-29: PAID means the invoiced amount was paid).
    """
    if state.status not in PAID_STATUSES or state.paid_amount is None:
        return False
    try:
        return Decimal(state.paid_amount) >= Decimal(expected_total)
    except InvalidOperation:
        return False


class ExecutionService:
    def __init__(self, gateway: PayPalGateway, journal: ExecutionJournal) -> None:
        self._gateway = gateway
        self._journal = journal

    @property
    def gateway(self) -> PayPalGateway:
        """Read access for lazy reconciliation and the Sandbox payment shortcut."""
        return self._gateway

    # ---- public API ------------------------------------------------------------------

    def execute_replacement(
        self,
        *,
        proposal_id: str,
        original_invoice_id: str,
        new_invoice_number: str,
        new_amount: Money,
        recipient_email: str,
        request_id: str,
    ) -> ExecutionResult:
        # Validate the outbound request before any PayPal call (raises on bad input).
        request = NewInvoiceReq(
            invoice_number=new_invoice_number, amount=new_amount, recipient_email=recipient_email
        )
        snapshot = self._journal.load(proposal_id) or ExecutionSnapshot(request_id=request_id)
        run = _Run(proposal_id, original_invoice_id, ProposalStatus.EXECUTING, snapshot)

        # Idempotent replay: never repeat a step that is already persisted.
        if snapshot.new_sent:
            run.steps.append("already_executed")
            return run.result(ProposalStatus.EXECUTED)
        if snapshot.original_cancelled:
            run.steps.append("awaiting_reconciliation")
            return run.result(ProposalStatus.NEEDS_RECONCILIATION)

        # 1. Preflight (allowlist): the original must be cancellable and unpaid.
        original = self._read(original_invoice_id)
        if original is None or not _is_cancellable(original):
            detail = "unreadable" if original is None else f"in status {original.status}"
            return self._abort(
                run,
                f"Preflight aborted: original invoice {detail}.",
                paypal_ref=original_invoice_id,
            )
        run.steps.append("preflight_ok")

        # 2. Create the draft once; a persisted draft_id is reused, never recreated.
        draft_id = run.snapshot.draft_id
        if draft_id is None:
            try:
                draft = self._gateway.create_draft(request, run.snapshot.request_id)
            except PayPalError as err:
                return self._abort(run, f"Draft creation failed: {err.code}.")
            draft_id = draft.id
            run.snapshot = replace(run.snapshot, draft_id=draft_id)
            run.steps.append("draft_created")
            self._emit(
                run,
                ExecutionAction.DRAFT_CREATED,
                Severity.INFO,
                f"Draft {draft_id} created.",
                paypal_ref=draft_id,
            )
        draft_state = self._read(draft_id)
        if draft_state is None or draft_state.status != DRAFT_STATUS:
            return self._abort(
                run,
                f"Draft {draft_id} is not in DRAFT state; aborting before cancel.",
                paypal_ref=draft_id,
            )

        # 3. Cancel the original. Never infer 'still open' from the error alone.
        outcome, cancel_code = self._cancel_original(original_invoice_id)
        if outcome is CancelOutcome.STILL_OPEN:
            return self._abort(
                run,
                f"Cancel failed ({cancel_code}); original confirmed open, draft rolled back.",
                paypal_ref=original_invoice_id,
            )
        if outcome is CancelOutcome.UNKNOWN:
            self._emit(
                run,
                ExecutionAction.NEEDS_RECONCILIATION,
                Severity.CRITICAL,
                f"Cancel outcome unknown ({cancel_code}); draft {draft_id} kept for reconcile.",
                to=ProposalStatus.NEEDS_RECONCILIATION,
                paypal_ref=original_invoice_id,
            )
            return run.result(ProposalStatus.NEEDS_RECONCILIATION)
        run.snapshot = replace(run.snapshot, original_cancelled=True)
        run.steps.append("original_cancelled")
        cancelled_summary = f"Original {original_invoice_id} cancelled."
        if cancel_code:
            cancelled_summary = (
                f"Original {original_invoice_id} cancelled (confirmed by re-read "
                f"after {cancel_code})."
            )
        self._emit(
            run,
            ExecutionAction.ORIGINAL_CANCELLED,
            Severity.INFO,
            cancelled_summary,
            paypal_ref=original_invoice_id,
        )

        # 4. Send the draft. The cancel cannot be undone: a failure needs reconciliation.
        try:
            self._gateway.send_invoice(draft_id)
        except PayPalError as err:
            self._emit(
                run,
                ExecutionAction.NEEDS_RECONCILIATION,
                Severity.CRITICAL,
                f"Send failed ({err.code}); original cancelled, draft {draft_id} unsent.",
                to=ProposalStatus.NEEDS_RECONCILIATION,
                paypal_ref=draft_id,
            )
            return run.result(ProposalStatus.NEEDS_RECONCILIATION)
        run.snapshot = replace(run.snapshot, new_sent=True)
        run.steps.append("draft_sent")
        self._emit(
            run,
            ExecutionAction.INVOICE_SENT,
            Severity.INFO,
            f"Draft {draft_id} sent to customer.",
            paypal_ref=draft_id,
        )
        self._emit(
            run,
            ExecutionAction.COMPLETED,
            Severity.INFO,
            "Replacement completed successfully.",
            to=ProposalStatus.EXECUTED,
            paypal_ref=draft_id,
        )
        return run.result(ProposalStatus.EXECUTED)

    def reconcile(self, *, proposal_id: str, original_invoice_id: str) -> ExecutionResult:
        """Resolve ``NEEDS_RECONCILIATION`` from live PayPal state. Never cancels (DEC-27)."""
        snapshot = self._journal.load(proposal_id)
        if snapshot is None or snapshot.draft_id is None:
            raise ExecutionStateError(f"Proposal {proposal_id} has no persisted draft to reconcile")
        draft_id = snapshot.draft_id
        run = _Run(
            proposal_id,
            original_invoice_id,
            ProposalStatus.NEEDS_RECONCILIATION,
            snapshot,
            source="RECONCILIATION",
            steps=["reconcile_started"],
        )

        original = self._read(original_invoice_id)
        draft = self._read(draft_id)
        if original is None or draft is None:
            return self._remain(run, "PayPal state unreadable; nothing was changed.", draft_id)
        original_cancelled = original.status == CANCELLED_STATUS

        if draft.status == SENT_STATUS:
            if not original_cancelled:
                return self._remain(
                    run,
                    "Draft is SENT but the original is not CANCELLED; manual review required.",
                    draft_id,
                )
            return self._complete_reconciliation(run, draft_id, "Draft was already sent.")

        if draft.status == DRAFT_STATUS:
            if original_cancelled:
                try:
                    self._gateway.send_invoice(draft_id)
                except PayPalError as err:
                    return self._remain(run, f"Reconcile send failed ({err.code}).", draft_id)
                run.steps.append("draft_sent_on_retry")
                return self._complete_reconciliation(
                    run, draft_id, f"Draft {draft_id} sent on retry."
                )
            if _is_cancellable(original):
                return self._abort(
                    run,
                    "Original confirmed open; draft discarded, no second invoice created.",
                    paypal_ref=draft_id,
                )

        return self._remain(
            run,
            f"Unexpected state: original {original.status}, draft {draft.status}.",
            draft_id,
        )

    # ---- internals -------------------------------------------------------------------

    def _read(self, invoice_id: str) -> PayPalInvoiceState | None:
        try:
            return self._gateway.get_invoice(invoice_id)
        except PayPalError:
            return None

    def _cancel_original(self, original_invoice_id: str) -> tuple[CancelOutcome, str]:
        """After ANY cancel error, re-read PayPal: an error never proves the original is open."""
        try:
            self._gateway.cancel_invoice(original_invoice_id)
        except PayPalError as err:
            error_code = err.code
        else:
            return CancelOutcome.CANCELLED, ""
        state = self._read(original_invoice_id)
        if state is None:
            return CancelOutcome.UNKNOWN, error_code
        if state.status == CANCELLED_STATUS:
            return CancelOutcome.CANCELLED, error_code
        if _is_cancellable(state):
            return CancelOutcome.STILL_OPEN, error_code
        return CancelOutcome.UNKNOWN, error_code

    def _emit(
        self,
        run: _Run,
        action: ExecutionAction,
        severity: Severity,
        summary: str,
        *,
        to: ProposalStatus | None = None,
        paypal_ref: str | None = None,
    ) -> None:
        self._journal.record(
            StepRecord(
                proposal_id=run.proposal_id,
                action=action,
                severity=severity,
                summary=summary,
                snapshot=run.snapshot,
                state_from=run.state_from if to is not None else None,
                state_to=to,
                source=run.source,
                paypal_ref=paypal_ref,
            )
        )

    def _rollback_draft(self, run: _Run) -> None:
        """Delete the persisted draft. A failed delete leaves an audited orphan (WARN)."""
        draft_id = run.snapshot.draft_id
        if draft_id is None:
            return
        try:
            self._gateway.delete_draft(draft_id)
        except PayPalError as err:
            self._emit(
                run,
                ExecutionAction.DRAFT_DELETED,
                Severity.WARN,
                f"Orphan draft {draft_id}: delete failed ({err.code}); reconcile cleans it up.",
                paypal_ref=draft_id,
            )
            return
        run.snapshot = replace(run.snapshot, draft_id=None)
        run.steps.append("draft_deleted")
        self._emit(
            run,
            ExecutionAction.DRAFT_DELETED,
            Severity.INFO,
            f"Draft {draft_id} deleted.",
            paypal_ref=draft_id,
        )

    def _abort(self, run: _Run, summary: str, *, paypal_ref: str | None = None) -> ExecutionResult:
        """Fail while the original is untouched: discard any draft, then record FAILED."""
        self._rollback_draft(run)
        self._emit(
            run,
            ExecutionAction.FAILED,
            Severity.CRITICAL,
            summary,
            to=ProposalStatus.FAILED,
            paypal_ref=paypal_ref,
        )
        return run.result(ProposalStatus.FAILED)

    def _remain(self, run: _Run, summary: str, draft_id: str) -> ExecutionResult:
        """Reconcile cannot decide: stay in NEEDS_RECONCILIATION (CRITICAL, no transition)."""
        self._emit(
            run,
            ExecutionAction.NEEDS_RECONCILIATION,
            Severity.CRITICAL,
            summary,
            paypal_ref=draft_id,
        )
        return run.result(ProposalStatus.NEEDS_RECONCILIATION)

    def _complete_reconciliation(self, run: _Run, draft_id: str, summary: str) -> ExecutionResult:
        run.snapshot = replace(run.snapshot, original_cancelled=True, new_sent=True)
        self._emit(
            run,
            ExecutionAction.RECONCILED,
            Severity.INFO,
            summary,
            to=ProposalStatus.EXECUTED,
            paypal_ref=draft_id,
        )
        return run.result(ProposalStatus.EXECUTED)
