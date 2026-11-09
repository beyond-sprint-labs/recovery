"""Webhook service: idempotency + state transition on INVOICING.INVOICE.PAID (F1-19)."""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.schemas import Actor, Severity
from app.core.states import ProposalStatus, assert_transition
from app.repositories.proposals_repo import ProposalsRepo
from app.repositories.webhook_events_repo import WebhookEventsRepo
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(
        self,
        *,
        session: Session,
        proposals: ProposalsRepo,
        events: WebhookEventsRepo,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._proposals = proposals
        self._events = events
        self._audit = audit

    def process_payment_paid(self, event_id: str, draft_id: str) -> bool:
        """Handle INVOICING.INVOICE.PAID.

        Returns True if the event was processed, False if it was a duplicate. The whole
        operation runs in ONE transaction: either the event is marked as processed AND the
        proposal moves to PAID, or nothing happens and PayPal retries.
        """
        # 1. Idempotency: the UNIQUE event_id is the real defence.
        if not self._events.register(event_id, "INVOICING.INVOICE.PAID"):
            logger.info("Duplicate webhook event %s ignored", event_id)
            return False

        # 2. Correlate the PayPal invoice (draft_id) with our proposal.
        proposal = self._proposals.find_by_draft_id(draft_id)
        if proposal is None:
            # Not our invoice, or an unexpected event. The event is registered, do nothing else.
            logger.warning("No proposal found for draft_id %s", draft_id)
            return True

        # 3. Only EXECUTED proposals can move to PAID.
        if proposal.status is not ProposalStatus.EXECUTED:
            if proposal.status in (ProposalStatus.EXECUTING, ProposalStatus.NEEDS_RECONCILIATION):
                # In-flight: do not acknowledge, ask PayPal to retry.
                self._session.rollback()
                raise HTTPException(status_code=409, detail="Proposal still executing; retry later")
            logger.info(
                "Proposal %s is in %s; ignoring PAID event",
                proposal.proposal_id,
                proposal.status.value,
            )
            self._session.commit()  # commit the event registration so we don't process it again
            return True

        # 4. Compare-and-set EXECUTED -> PAID. If another path wins, the event is still safe.
        assert_transition(ProposalStatus.EXECUTED, ProposalStatus.PAID)
        now = datetime.now(UTC).replace(microsecond=0)

        if self._proposals.mark_paid(proposal_id=proposal.proposal_id, now=now):
            self._audit.record(
                actor=Actor(type="PAYPAL", id="paypal_invoicing"),
                action="PAYMENT_CONFIRMED",
                severity=Severity.INFO,
                summary=f"Payment confirmed via webhook on PayPal invoice {draft_id}",
                invoice_id=proposal.invoice_id,
                proposal_id=proposal.proposal_id,
                state_from=ProposalStatus.EXECUTED,
                state_to=ProposalStatus.PAID,
                paypal_called=True,
                source="WEBHOOK",
                paypal_ref=draft_id,
            )
        # 5. Commit the event registration + transition + audit together.
        self._session.commit()
        return True
