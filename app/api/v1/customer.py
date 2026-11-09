"""Customer portal endpoints (F1-13 slice 3). Parse, delegate, serialize: nothing else."""

from fastapi import APIRouter, Response

from app.core.deps import RecoveryServiceDep
from app.core.schemas import CustomerProposalView, RespondIn, RespondOut

router = APIRouter(tags=["customer"])

_NO_STORE = "no-store"


@router.get("/customer/proposals/{token}", response_model=CustomerProposalView)
def get_customer_proposal(
    token: str, response: Response, service: RecoveryServiceDep
) -> CustomerProposalView:
    """Single pre-approved alternative. Does not consume the token."""
    response.headers["Cache-Control"] = _NO_STORE
    return service.get_customer_proposal(token)


@router.post("/customer/proposals/{token}/respond", response_model=RespondOut)
def respond_to_proposal(
    token: str, body: RespondIn, response: Response, service: RecoveryServiceDep
) -> RespondOut:
    """ACCEPT or DECLINE. FAILED and NEEDS_RECONCILIATION are persisted business results: 200."""
    response.headers["Cache-Control"] = _NO_STORE
    return service.respond_to_proposal(token, body)
