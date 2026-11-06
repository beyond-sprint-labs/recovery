from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_recovery_service
from app.core.schemas import RespondIn
from app.services.recovery_service import RecoveryService

router = APIRouter(prefix="/customer", tags=["Customer"])


@router.post(
    "/proposals/{proposal_id}/respond",
    responses={409: {"description": "Token expired or already used"}},
)
def respond_to_proposal(
    proposal_id: str,
    body: RespondIn,
    token: str,
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    try:
        return service.respond_to_proposal(proposal_id, token, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
