"""Incremental audit trail endpoint polled by the live AG Grid (F1-22)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import AuditServiceDep
from app.core.schemas import AuditEventsPage
from app.services.audit_service import MAX_PAGE_LIMIT

router = APIRouter(tags=["audit"])


@router.get("/audit-events", response_model=AuditEventsPage)
def list_audit_events(
    service: AuditServiceDep,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = 100,
    proposal_id: Annotated[str | None, Query(max_length=64)] = None,
) -> AuditEventsPage:
    return service.list_events(after_seq=after_seq, limit=limit, proposal_id=proposal_id)
