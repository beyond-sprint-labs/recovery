"""Proposal endpoints (F1-13 slices 1-2, F1-18b). Parse, delegate, serialize: nothing else."""

from typing import Annotated

from fastapi import APIRouter, Header

from app.core.deps import RecoveryServiceDep
from app.core.schemas import (
    ApproveIn,
    ApproveOut,
    CreateProposalIn,
    Policy,
    ProposalOut,
    ProposalStatusOut,
    RejectIn,
)

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
    """Also reconciles lazily with PayPal when an EXECUTED proposal may have been paid."""
    return service.get_proposal(proposal_id)


@router.post("/proposals/{proposal_id}/approve", response_model=ApproveOut)
def approve_proposal(proposal_id: str, body: ApproveIn, service: RecoveryServiceDep) -> ApproveOut:
    """Approve ONE alternative. The clear customer token appears only in this response."""
    return service.approve_proposal(proposal_id, body)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalStatusOut)
def reject_proposal(
    proposal_id: str, body: RejectIn, service: RecoveryServiceDep
) -> ProposalStatusOut:
    """Reject a proposal that is waiting for the merchant."""
    return service.reject_proposal(proposal_id, body)


@router.post("/proposals/{proposal_id}/reconcile", response_model=ProposalStatusOut)
def reconcile_proposal(proposal_id: str, service: RecoveryServiceDep) -> ProposalStatusOut:
    """Resume a NEEDS_RECONCILIATION proposal from live PayPal state (DEC-27).

    Only the pending send is retried, never the cancellation. A proposal that stays in
    NEEDS_RECONCILIATION is a persisted business result and answers HTTP 200.
    """
    return service.reconcile_proposal(proposal_id)


@router.post("/proposals/{proposal_id}/sandbox/record-payment", response_model=ProposalStatusOut)
def record_sandbox_payment(proposal_id: str, service: RecoveryServiceDep) -> ProposalStatusOut:
    """Merchant-recorded payment (Sandbox). The amount never comes from the request."""
    return service.record_sandbox_payment(proposal_id)
