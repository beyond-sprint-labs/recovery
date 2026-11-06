from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.repositories.audit_repo import AuditRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.services.audit_service import AuditService
from app.services.recovery_service import RecoveryService


def get_db():
    with get_session_factory()() as session:
        yield session


def get_recovery_service(db: Annotated[Session, Depends(get_db)]) -> RecoveryService:
    repo = ProposalsRepo(db)
    audit = AuditService(AuditRepo(db))
    return RecoveryService(repo=repo, audit=audit)
