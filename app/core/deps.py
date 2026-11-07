"""Dependency wiring (``Depends``) shared by routers."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agent.mock_agent import ScriptedAgent
from app.core.config import Settings, get_settings
from app.core.db import get_session_factory
from app.core.errors import UpstreamError
from app.repositories.audit_repo import AuditRepo
from app.repositories.invoices_repo import InvoicesRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.repositories.unit_of_work import SqlAlchemyUnitOfWork
from app.services.audit_service import AuditService
from app.services.recovery_service import AgentBinding, AgentFactory, RecoveryService


def get_db() -> Iterator[Session]:
    """Yield a database session and safely close it."""
    with get_session_factory()() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]


def get_audit_service(session: DbSession) -> AuditService:
    return AuditService(AuditRepo(session))


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]


def get_agent_factory(settings: SettingsDep) -> AgentFactory:
    """Build the agent for one request.

    ``scenario_id`` (already filtered by the service) or ``AGENT_MODE=scripted`` selects the
    deterministic agent: figures still come from the real finance engine. The LLM agent
    arrives with F1-20; until then ``AGENT_MODE=llm`` without a scenario fails before any
    write (502, no state change).
    """

    def build(scenario_id: str | None) -> AgentBinding:
        if scenario_id is not None or settings.agent_mode == "scripted":
            return AgentBinding(agent=ScriptedAgent(scenario_id), mode="DEMO")
        raise UpstreamError("AGENT_UNAVAILABLE", "The LLM agent is not available yet")

    return build


AgentFactoryDep = Annotated[AgentFactory, Depends(get_agent_factory)]


def get_recovery_service(
    session: DbSession,
    settings: SettingsDep,
    audit: AuditServiceDep,
    agent_factory: AgentFactoryDep,
) -> RecoveryService:
    return RecoveryService(
        invoices=InvoicesRepo(session),
        proposals=ProposalsRepo(session),
        audit=audit,
        uow=SqlAlchemyUnitOfWork(session),
        agent_factory=agent_factory,
        settings=settings,
    )


RecoveryServiceDep = Annotated[RecoveryService, Depends(get_recovery_service)]
