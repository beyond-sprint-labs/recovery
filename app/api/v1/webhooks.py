"""PayPal Webhook receiver (F1-19). Verifies the signature, then processes the event."""

import json

from fastapi import APIRouter, HTTPException, Request

from app.core.deps import DbSession, WebhookVerifierDep
from app.repositories.audit_repo import AuditRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.repositories.webhook_events_repo import WebhookEventsRepo
from app.services.audit_service import AuditService
from app.services.webhook_service import WebhookService

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/paypal")
async def paypal_webhook(
    request: Request,
    db: DbSession,
    verifier: WebhookVerifierDep,
) -> dict[str, bool]:
    """Receive PayPal events, verify the signature, and process the payment.

    A signature failure returns 401 without touching the database, so PayPal retries the
    delivery. A duplicate event is acknowledged with 200 (the receiver is idempotent).
    """
    raw_body = await request.body()
    headers = dict(request.headers)

    # 1. Verify the signature using PayPal's API (DEC-24). No DB transaction is open yet.
    if not verifier.verify(headers, raw_body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 2. Parse the event envelope.
    try:
        event = json.loads(raw_body)
        event_id: str = event["id"]
        event_type: str = event["event_type"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Malformed event body") from None

    # 3. Only INVOICING.INVOICE.PAID moves a proposal to PAID.
    if event_type == "INVOICING.INVOICE.PAID":
        try:
            draft_id: str = event["resource"]["invoice"]["id"]
        except (KeyError, TypeError):
            raise HTTPException(status_code=400, detail="Missing invoice id") from None

        service = WebhookService(
            session=db,
            proposals=ProposalsRepo(db),
            events=WebhookEventsRepo(db),
            audit=AuditService(AuditRepo(db)),
        )
        service.process_payment_paid(event_id, draft_id)

    return {"received": True}
