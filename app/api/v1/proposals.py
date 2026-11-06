from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_recovery_service
from app.core.schemas import ApproveIn, CreateProposalIn, ErrorOut
from app.services.recovery_service import RecoveryService

router = APIRouter(tags=["Proposals"])


@router.post(
    "/invoices/{invoice_id}/proposals",
    responses={422: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def create_proposal(
    invoice_id: str,
    body: CreateProposalIn,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    try:
        proposal = service.create_proposal(invoice_id, body, idempotency_key)
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/proposals/{proposal_id}/approve",
    responses={422: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def approve_proposal(
    proposal_id: str,
    body: ApproveIn,
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    try:
        return service.approve_proposal(proposal_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
