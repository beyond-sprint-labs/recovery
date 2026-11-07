"""Proposal endpoints (F1-13, slice 1). Parse, delegate, serialize: nothing else."""

from typing import Annotated

from fastapi import APIRouter, Header

from app.core.deps import RecoveryServiceDep
from app.core.schemas import CreateProposalIn, Policy, ProposalOut

router = APIRouter(tags=["proposals"])


@router.get("/policy", response_model=Policy)
def get_policy(service: RecoveryServiceDep) -> Policy:
    """Read-only merchant policy; it can never be supplied by a client (DEC-17)."""
    return service.get_policy()


@router.post("/invoices/{invoice_id}/proposals", response_model=ProposalOut)
def create_proposal(
    invoice_id: str,
    body: CreateProposalIn,
    service: RecoveryServiceDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> ProposalOut:
    """BLOCKED is a business result and answers HTTP 200 (DEC-05)."""
    return service.create_proposal(invoice_id, body, idempotency_key)


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: str, service: RecoveryServiceDep) -> ProposalOut:
    return service.get_proposal(proposal_id)
