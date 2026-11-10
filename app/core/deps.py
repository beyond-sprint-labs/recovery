"""Dependency wiring (``Depends``) shared by routers."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated, Final

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.agent.agent import NegotiationAgent
from app.agent.fallback_agent import FallbackAgent
from app.agent.gemini_client import GeminiClient
from app.agent.mock_agent import ScriptedAgent
from app.core.config import Settings, get_settings
from app.core.db import get_session_factory
from app.core.errors import UpstreamError
from app.paypal.factory import build_gateway, build_webhook_verifier
from app.paypal.gateway import PayPalError, PayPalGateway
from app.paypal.signature import WebhookVerifier
from app.repositories.audit_repo import AuditRepo
from app.repositories.execution_journal import SqlExecutionJournal
from app.repositories.invoices_repo import InvoicesRepo
from app.repositories.proposals_repo import ProposalsRepo
from app.repositories.unit_of_work import SqlAlchemyUnitOfWork
from app.services.audit_service import AuditService
from app.services.execution_service import ExecutionService
from app.services.recovery_service import (
    AgentBinding,
    AgentFactory,
    ExecutionProvider,
    RecoveryService,
)


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
    """Build the configured negotiation agent for one request."""

    def build(scenario_id: str | None) -> AgentBinding:
        # The service filters scenario IDs before invoking this factory.
        if scenario_id is not None or settings.agent_mode == "scripted":
            return AgentBinding(
                agent=ScriptedAgent(scenario_id),
                mode="DEMO",
            )

        if settings.llm_provider != "gemini":
            raise UpstreamError(
                "AGENT_CONFIG_INVALID",
                "Unsupported LLM provider",
            )

        if not settings.llm_model or not settings.llm_api_key.get_secret_value():
            raise UpstreamError(
                "AGENT_CONFIG_INVALID",
                "LLM configuration is incomplete",
            )

        client = GeminiClient(settings)
        primary = NegotiationAgent(
            client=client,
            text_client=client,
        )

        return AgentBinding(
            agent=FallbackAgent(primary),
            mode="LLM",
        )

    return build


AgentFactoryDep = Annotated[AgentFactory, Depends(get_agent_factory)]


@lru_cache
def get_paypal_gateway() -> PayPalGateway:
    """Process-wide gateway, selected by ``PAYPAL_MODE`` only (never by request data).

    Cached because the mock keeps its invoices in memory and the real client caches its OAuth
    token. Tests clear it with ``get_paypal_gateway.cache_clear()``.
    """
    return build_gateway(get_settings())


def get_execution_provider(session: DbSession) -> ExecutionProvider:
    """Lazy factory of ``ExecutionService``: PayPal is only touched when a method needs it.

    A BLOCKED proposal, a policy read or an audit poll never builds the gateway, so a missing
    PayPal credential cannot break them. The journal gets its own sessions, bound to the same
    engine as the request session, and the service never shares a transaction with it.
    """
    journal_sessions = sessionmaker(
        bind=session.get_bind(), autoflush=False, expire_on_commit=False
    )

    def provide() -> ExecutionService:
        try:
            gateway = get_paypal_gateway()
        except PayPalError as err:
            raise UpstreamError(err.code, err.message) from err
        return ExecutionService(gateway, SqlExecutionJournal(journal_sessions))

    return provide


ExecutionProviderDep = Annotated[ExecutionProvider, Depends(get_execution_provider)]


def get_recovery_service(
    session: DbSession,
    settings: SettingsDep,
    audit: AuditServiceDep,
    agent_factory: AgentFactoryDep,
    execution_provider: ExecutionProviderDep,
) -> RecoveryService:
    return RecoveryService(
        invoices=InvoicesRepo(session),
        proposals=ProposalsRepo(session),
        audit=audit,
        uow=SqlAlchemyUnitOfWork(session),
        agent_factory=agent_factory,
        settings=settings,
        execution_provider=execution_provider,
    )


RecoveryServiceDep = Annotated[RecoveryService, Depends(get_recovery_service)]


def get_webhook_verifier(settings: SettingsDep) -> WebhookVerifier:
    """Build the verifier selected by ``PAYPAL_MODE`` only (never by request data).

    In ``mock`` mode, the mock verifier accepts everything (so integration tests and the
    local demo work without contacting PayPal). In ``real`` mode, the official
    verify-webhook-signature endpoint is called (DEC-24, no SSRF, no X.509 download).
    """
    return build_webhook_verifier(settings)


WebhookVerifierDep = Annotated[WebhookVerifier, Depends(get_webhook_verifier)]

MAX_WEBHOOK_BODY_BYTES: Final = 65_536


async def get_raw_body(request: Request) -> bytes:
    """Read raw webhook bytes with an early abort size cap."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook body too large")
    return bytes(received)


RawBodyDep = Annotated[bytes, Depends(get_raw_body)]
