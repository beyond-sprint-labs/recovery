"""Execution Service: orchestrates the anti-double-charge replacement sequence.

Rules:
1. Preflight: Never cancel an invoice that has payments (PARTIALLY_PAID/PAID).
2. Create draft BEFORE cancelling the original.
3. If cancel fails, delete the draft immediately (rollback).
4. If send fails after cancel, transition to NEEDS_RECONCILIATION.
"""

from dataclasses import dataclass

from app.core.schemas import Actor, ProposalStatus, Severity
from app.paypal.gateway import (
    NewInvoiceReq,
    PayPalError,
    PayPalGateway,
)
from app.services.audit_service import AuditService


@dataclass(frozen=True)
class ExecutionResult:
    status: ProposalStatus
    new_invoice_id: str | None
    original_invoice_id: str | None
    steps: list[str]


class ExecutionService:
    def __init__(
        self,
        gateway: PayPalGateway,
        audit: AuditService,
    ) -> None:
        self._gateway = gateway
        self._audit = audit

    def execute_replacement(
        self,
        *,
        proposal_id: str,
        original_invoice_id: str,
        new_invoice_number: str,
        new_amount: str,
        request_id: str,
    ) -> ExecutionResult:
        steps: list[str] = []
        system = Actor(type="SYSTEM", id="execution_service")

        # ---- 1. PREFLIGHT ------------------------------------------------
        try:
            original = self._gateway.get_invoice(original_invoice_id)
        except PayPalError as err:
            self._audit.record(
                actor=system,
                action="PREFLIGHT_FAILED",
                severity=Severity.CRITICAL,
                summary=f"Could not fetch original invoice: {err.code}",
                proposal_id=proposal_id,
                paypal_called=True,
                paypal_ref=original_invoice_id,
            )
            return ExecutionResult(ProposalStatus.FAILED, None, original_invoice_id, steps)

        if original.status in {"PARTIALLY_PAID", "PAID", "MARKED_AS_PAID"}:
            self._audit.record(
                actor=system,
                action="PREFLIGHT_ABORTED",
                severity=Severity.CRITICAL,
                summary=f"Original invoice is {original.status}; cannot cancel.",
                proposal_id=proposal_id,
                paypal_called=True,
                paypal_ref=original_invoice_id,
            )
            return ExecutionResult(ProposalStatus.FAILED, None, original_invoice_id, steps)
        steps.append("preflight_ok")

        # ---- 2. CREATE DRAFT ---------------------------------------------
        try:
            draft_req = NewInvoiceReq(
                invoice_number=new_invoice_number,
                amount=new_amount,
                recipient_email=None,  # gateway uses PAYPAL_SANDBOX_BUYER_EMAIL
            )
            draft = self._gateway.create_draft(draft_req, request_id)
        except PayPalError as err:
            self._audit.record(
                actor=system,
                action="PAYPAL_DRAFT_FAILED",
                severity=Severity.CRITICAL,
                summary=f"Draft creation failed: {err.code}",
                proposal_id=proposal_id,
                paypal_called=True,
            )
            return ExecutionResult(ProposalStatus.FAILED, None, original_invoice_id, steps)
        steps.append("draft_created")
        self._audit.record(
            actor=system,
            action="PAYPAL_DRAFT_CREATED",
            severity=Severity.INFO,
            summary=f"Draft {draft.id} created.",
            proposal_id=proposal_id,
            paypal_called=True,
            paypal_ref=draft.id,
        )

        # ---- 3. CANCEL ORIGINAL ------------------------------------------
        try:
            self._gateway.cancel_invoice(original_invoice_id)
        except PayPalError as err:
            # Rollback: delete the draft we just created
            try:
                self._gateway.delete_draft(draft.id)
                steps.append("draft_deleted_after_cancel_failure")
            except PayPalError as cleanup_err:
                # Orphan draft — audited as WARN; reconcile will clean up later
                self._audit.record(
                    actor=system,
                    action="PAYPAL_DRAFT_DELETED",
                    severity=Severity.WARN,
                    summary=f"Orphan draft {draft.id}: cleanup failed ({cleanup_err.code}).",
                    proposal_id=proposal_id,
                    paypal_called=True,
                    paypal_ref=draft.id,
                )
            self._audit.record(
                actor=system,
                action="PAYPAL_ORIGINAL_CANCELLED",
                severity=Severity.CRITICAL,
                summary=f"Cancel failed: {err.code}. Draft {draft.id} cleaned up.",
                proposal_id=proposal_id,
                paypal_called=True,
                paypal_ref=original_invoice_id,
            )
            return ExecutionResult(ProposalStatus.FAILED, None, original_invoice_id, steps)
        steps.append("original_cancelled")
        self._audit.record(
            actor=system,
            action="PAYPAL_ORIGINAL_CANCELLED",
            severity=Severity.INFO,
            summary=f"Original {original_invoice_id} cancelled.",
            proposal_id=proposal_id,
            paypal_called=True,
            paypal_ref=original_invoice_id,
        )

        # ---- 4. SEND DRAFT -----------------------------------------------
        try:
            sent = self._gateway.send_invoice(draft.id)
        except PayPalError as err:
            # Cannot un-cancel. Move to NEEDS_RECONCILIATION.
            self._audit.record(
                actor=system,
                action="PAYPAL_INVOICE_SENT",
                severity=Severity.CRITICAL,
                summary=f"Send failed: {err.code}. Awaiting reconciliation.",
                proposal_id=proposal_id,
                paypal_called=True,
                paypal_ref=draft.id,
            )
            return ExecutionResult(
                ProposalStatus.NEEDS_RECONCILIATION, draft.id, original_invoice_id, steps
            )
        steps.append("draft_sent")
        self._audit.record(
            actor=system,
            action="PAYPAL_INVOICE_SENT",
            severity=Severity.INFO,
            summary=f"Draft {sent.id} sent to customer.",
            proposal_id=proposal_id,
            paypal_called=True,
            paypal_ref=sent.id,
        )

        self._audit.record(
            actor=system,
            action="EXECUTION_COMPLETED",
            severity=Severity.INFO,
            summary="Replacement completed successfully.",
            proposal_id=proposal_id,
            state_from=ProposalStatus.EXECUTING,
            state_to=ProposalStatus.EXECUTED,
            paypal_called=True,
        )
        return ExecutionResult(ProposalStatus.EXECUTED, draft.id, original_invoice_id, steps)

    def reconcile(
        self,
        *,
        proposal_id: str,
        draft_id: str,
        original_invoice_id: str,
    ) -> ExecutionResult:
        """Retry sending a draft that failed after the original was cancelled."""
        steps: list[str] = ["reconcile_started"]
        system = Actor(type="SYSTEM", id="execution_service")

        # 1. Check if the draft is still in DRAFT state (not sent yet)
        try:
            draft_state = self._gateway.get_invoice(draft_id)
        except PayPalError as err:
            self._audit.record(
                actor=system,
                action="RECONCILIATION_FAILED",
                severity=Severity.CRITICAL,
                summary=f"Could not fetch draft {draft_id}: {err.code}",
                proposal_id=proposal_id,
                paypal_called=True,
                paypal_ref=draft_id,
            )
            return ExecutionResult(
                ProposalStatus.NEEDS_RECONCILIATION, draft_id, original_invoice_id, steps
            )

        if draft_state.status == "SENT":
            # It was already sent! Just move to EXECUTED.
            self._audit.record(
                actor=system,
                action="RECONCILED",
                severity=Severity.INFO,
                summary="Draft was already sent; marking as EXECUTED.",
                proposal_id=proposal_id,
                source="RECONCILIATION",
                paypal_called=True,
                paypal_ref=draft_id,
            )
            return ExecutionResult(
                ProposalStatus.EXECUTED, draft_id, original_invoice_id, [*steps, "already_sent"]
            )

        if draft_state.status == "CANCELLED":
            # Orphan draft was cleaned up. Move to FAILED.
            self._audit.record(
                actor=system,
                action="RECONCILIATION_FAILED",
                severity=Severity.CRITICAL,
                summary="Draft was cancelled. Cannot recover.",
                proposal_id=proposal_id,
                source="RECONCILIATION",
                paypal_called=True,
                paypal_ref=draft_id,
            )
            return ExecutionResult(
                ProposalStatus.FAILED, draft_id, original_invoice_id, [*steps, "draft_cancelled"]
            )

        # 2. Try to send the draft again
        try:
            sent = self._gateway.send_invoice(draft_id)
        except PayPalError as err:
            self._audit.record(
                actor=system,
                action="RECONCILIATION_FAILED",
                severity=Severity.CRITICAL,
                summary=f"Reconcile send failed: {err.code}",
                proposal_id=proposal_id,
                source="RECONCILIATION",
                paypal_called=True,
                paypal_ref=draft_id,
            )
            return ExecutionResult(
                ProposalStatus.NEEDS_RECONCILIATION, draft_id, original_invoice_id, steps
            )

        self._audit.record(
            actor=system,
            action="RECONCILED",
            severity=Severity.INFO,
            summary=f"Reconciled successfully. Draft {sent.id} sent.",
            proposal_id=proposal_id,
            state_from=ProposalStatus.NEEDS_RECONCILIATION,
            state_to=ProposalStatus.EXECUTED,
            source="RECONCILIATION",
            paypal_called=True,
            paypal_ref=sent.id,
        )
        return ExecutionResult(
            ProposalStatus.EXECUTED, draft_id, original_invoice_id, [*steps, "draft_sent_on_retry"]
        )
