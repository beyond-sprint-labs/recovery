"""PayPal Webhook receiver (F1-19)."""

from fastapi import APIRouter, HTTPException, Request

from app.core.deps import DbSession, RawBodyDep, WebhookVerifierDep
from app.core.errors import UnauthorizedError
from app.core.schemas import Actor, Severity
from app.paypal.gateway import PayPalError
from app.repositories.audit_repo import AuditRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.repositories.webhook_events_repo import WebhookEventsRepo
from app.services.audit_service import AuditService
from app.services.webhook_service import WebhookService

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/paypal")
def paypal_webhook(
    request: Request,
    raw_body: RawBodyDep,
    db: DbSession,
    verifier: WebhookVerifierDep,
) -> dict[str, bool]:
    """Receive PayPal events, verify the signature, and process the payment."""
    audit = AuditService(AuditRepo(db))

    # 1. Verify signature
    try:
        is_authentic = verifier.verify(dict(request.headers), raw_body)
    except PayPalError as err:
        raise HTTPException(status_code=502, detail="PayPal verification unreachable") from err

    if not is_authentic:
        audit.record(
            actor=Actor(type="SYSTEM", id="webhook_receiver"),
            action="WEBHOOK_REJECTED",
            severity=Severity.WARN,
            summary="PayPal webhook rejected: invalid signature or untrusted cert_url",
            source="WEBHOOK",
        )
        db.commit()
        raise UnauthorizedError("INVALID_WEBHOOK_SIGNATURE", "Invalid webhook signature")

    # 2. Parse the event
    try:
        import json

        event = json.loads(raw_body)
        event_id: str = event["id"]
        event_type: str = event["event_type"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Malformed event body") from None

    # 3. Process
    if event_type == "INVOICING.INVOICE.PAID":
        try:
            draft_id: str = event["resource"]["invoice"]["id"]
        except (KeyError, TypeError):
            raise HTTPException(status_code=400, detail="Missing invoice id") from None

        service = WebhookService(
            session=db,
            proposals=ProposalsRepo(db),
            events=WebhookEventsRepo(db),
            audit=audit,
        )
        is_new = service.process_payment_paid(event_id, draft_id)
        if not is_new:
            return {"received": True, "duplicate": True}

    return {"received": True}
