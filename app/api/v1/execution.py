"""Execution endpoints (F1-18b): reconcile and sandbox record-payment."""

from fastapi import APIRouter, HTTPException

from app.core.deps import DbSession, ExecutionServiceDep, PayPalGatewayDep
from app.repositories.proposals_repo import ProposalsRepo

router = APIRouter(tags=["execution"])


@router.post("/proposals/{proposal_id}/reconcile")
def reconcile_proposal(
    proposal_id: str,
    service: ExecutionServiceDep,
    db: DbSession,
):
    """Retries sending a draft that failed after the original was cancelled."""
    repo = ProposalsRepo(db)
    proposal = repo.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    invoice_row = repo.get_invoice_for_proposal(proposal_id)
    if not invoice_row or not invoice_row.paypal_invoice_id:
        raise HTTPException(status_code=400, detail="No PayPal invoice found for this proposal")

    try:
        result = service.reconcile(
            proposal_id=proposal_id,
            original_invoice_id=invoice_row.paypal_invoice_id,
        )
        return {"status": result.status.value, "steps": result.steps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/proposals/{proposal_id}/sandbox/record-payment")
def record_payment_sandbox(
    proposal_id: str,
    db: DbSession,
    gateway: PayPalGatewayDep,
):
    """Sandbox shortcut: records a payment on the proposal's PayPal invoice."""
    repo = ProposalsRepo(db)
    invoice_row = repo.get_invoice_for_proposal(proposal_id)

    if not invoice_row or not invoice_row.paypal_invoice_id:
        raise HTTPException(status_code=400, detail="No PayPal invoice found for this proposal")

    try:
        gateway.record_payment(
            paypal_invoice_id=invoice_row.paypal_invoice_id,
            amount=invoice_row.balance,
        )
        return {"status": "PAYMENT_RECORDED", "paypal_ref": invoice_row.paypal_invoice_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
