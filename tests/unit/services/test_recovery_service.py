"""Service-level tests for RecoveryService (F1-13, slice 1)."""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.agent.schemas import AgentOutput
from app.core.config import get_settings
from app.core.errors import ConflictError, UnprocessableError
from app.core.models import CustomerRow, InvoiceRow
from app.core.schemas import Alternative, CreateProposalIn, CustomerIntent, Policy
from app.core.states import ProposalStatus
from app.finance import calculate_alternatives
from app.repositories.audit_repo import AuditRepo
from app.repositories.invoices_repo import InvoicesRepo
from app.repositories.proposals_repo import NewProposal, ProposalsRepo
from app.repositories.unit_of_work import SqlAlchemyUnitOfWork
from app.services.audit_service import AuditService
from app.services.recovery_service import (
    AgentBinding,
    RecoveryService,
    build_allowed_numbers,
    build_requested_terms,
    compute_request_hash,
)

DEFAULT_POLICY = Policy(
    currency="USD",
    max_discount_pct="15",
    min_down_payment_pct="20",
    max_installments=6,
    max_financing_rate_pct="2.0",
    merchant_discount_rate_pct="1.0",
)


@pytest.fixture
def seeded(db_session: Session) -> None:
    db_session.add(CustomerRow(id="CUS-001", name="Acme Corp", email="billing@example.com"))
    db_session.flush()
    db_session.add(
        InvoiceRow(
            id="INV-001",
            customer_id="CUS-001",
            customer_name="Acme Corp",
            currency="USD",
            balance="1000.00",
            due_date="2026-10-15",
            status="OVERDUE",
            paypal_invoice_id=None,
        )
    )
    db_session.commit()


class _SpyAgent:
    """Records whether a transaction was open while the agent ran."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.in_transaction_during_run: bool | None = None

    def run(self, sanitized_message: str, tool_runner: object) -> AgentOutput:
        self.in_transaction_during_run = self._session.in_transaction()
        return AgentOutput(intent=CustomerIntent())

    def explain_alternatives(self, engine_result: Mapping[str, object]) -> str:
        raise AssertionError("must not be called without an intent")

    def draft_customer_message(self, engine_result: Mapping[str, object]) -> str:
        raise AssertionError("must not be called without an intent")


class _ExplodingAgent(_SpyAgent):
    def run(self, sanitized_message: str, tool_runner: object) -> AgentOutput:
        raise RuntimeError("boom")


class _BlindProposalsRepo(ProposalsRepo):
    """Hides the winner on the first lookup, like a request that lost the race."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._first = True

    def get_by_idempotency_key(self, idempotency_key: str):  # type: ignore[no-untyped-def]
        if self._first:
            self._first = False
            return None
        return super().get_by_idempotency_key(idempotency_key)


def _service(
    session: Session, agent: _SpyAgent, proposals: ProposalsRepo | None = None
) -> RecoveryService:
    return RecoveryService(
        invoices=InvoicesRepo(session),
        proposals=proposals or ProposalsRepo(session),
        audit=AuditService(AuditRepo(session)),
        uow=SqlAlchemyUnitOfWork(session),
        agent_factory=lambda _scenario: AgentBinding(agent=agent, mode="DEMO"),
        settings=get_settings(),
    )


# --- pure helpers ---------------------------------------------------------------------------------


def test_defaults_match_the_golden_case() -> None:
    settlement, plan = build_requested_terms(
        CustomerIntent(preferred_installments=3), balance="1000.00", policy=DEFAULT_POLICY
    )
    assert settlement == {"discount_pct": "10"}
    assert plan == {"down_payment_pct": "30", "installments": 3, "periodic_rate_pct": "1.5"}


@pytest.mark.parametrize(
    ("available_now", "balance", "expected"),
    [
        ("300.00", "1000.00", "30"),
        ("333.33", "1000.00", "33.333"),
        ("100.00", "300.00", "33.3333"),
        ("1000.00", "1000.00", "99"),  # capped below 100 %
        ("0.00", "1000.00", "20"),  # floored to the policy minimum
    ],
)
def test_down_payment_is_derived_from_available_now(
    available_now: str, balance: str, expected: str
) -> None:
    _, plan = build_requested_terms(
        CustomerIntent(available_now=available_now), balance=balance, policy=DEFAULT_POLICY
    )
    assert plan["down_payment_pct"] == expected


def test_defaults_are_clamped_to_the_policy() -> None:
    policy = Policy(
        currency="USD",
        max_discount_pct="5",
        min_down_payment_pct="40",
        max_installments=2,
        max_financing_rate_pct="1.0",
        merchant_discount_rate_pct="1.0",
    )
    settlement, plan = build_requested_terms(CustomerIntent(), balance="1000.00", policy=policy)
    assert settlement == {"discount_pct": "5"}
    assert plan == {"down_payment_pct": "40", "installments": 2, "periodic_rate_pct": "1"}


def test_requested_terms_are_never_clamped_so_the_policy_gate_can_block_them() -> None:
    settlement, plan = build_requested_terms(
        CustomerIntent(requested_discount_pct="40", preferred_installments=12),
        balance="1000.00",
        policy=DEFAULT_POLICY,
    )
    assert settlement == {"discount_pct": "40"}
    assert plan["installments"] == 12


def test_allowed_numbers_are_narrow() -> None:
    result = calculate_alternatives(
        {
            "engine_version": "1.0.0",
            "invoice": {
                "id": "INV-001",
                "currency": "USD",
                "balance": "1000.00",
                "due_date": "2026-10-15",
                "as_of_date": "2026-11-11",
            },
            "alternatives": [
                {"type": "settlement_discount", "discount_pct": "10"},
                {
                    "type": "down_payment_installments",
                    "down_payment_pct": "30",
                    "installments": 3,
                    "periodic_rate_pct": "1.5",
                },
            ],
            "policy": DEFAULT_POLICY.model_dump(exclude={"currency"}),
        }
    )
    alternatives = [Alternative.model_validate(item) for item in result["alternatives"]]  # type: ignore[attr-defined]
    allowed = build_allowed_numbers(
        alternatives=alternatives,
        intent=CustomerIntent(preferred_installments=3),
        policy=DEFAULT_POLICY,
        invoice_id="INV-001",
        balance="1000.00",
    )
    assert Decimal("1021.10") in allowed.values
    assert Decimal("1006.91") in allowed.values
    assert Decimal("850.00") not in allowed.values
    # A blanket "small integers" allowance would let an invented "$5.00" through.
    assert Decimal("5") not in allowed.values
    # Schedule indices are not figures.
    assert Decimal("4") not in allowed.values
    assert "INV-001" in allowed.invoice_ids


# --- service behaviour ----------------------------------------------------------------------------


@pytest.mark.usefixtures("seeded")
def test_no_transaction_is_open_while_the_agent_runs(db_session: Session) -> None:
    agent = _SpyAgent(db_session)
    out = _service(db_session, agent).create_proposal(
        "INV-001", CreateProposalIn(customer_message="Can you help me?"), "key-no-tx-0001"
    )
    assert agent.in_transaction_during_run is False
    assert out.status is ProposalStatus.BLOCKED
    assert out.blocked_reasons[0].code == "CLARIFICATION_REQUIRED"
    assert out.audit_event is not None
    assert out.audit_event.severity.value == "WARN"


@pytest.mark.usefixtures("seeded")
def test_unexpected_agent_failure_is_persisted_as_blocked_not_left_drafted(
    db_session: Session,
) -> None:
    out = _service(db_session, _ExplodingAgent(db_session)).create_proposal(
        "INV-001", CreateProposalIn(customer_message="Please help"), "key-boom-000001"
    )
    assert out.status is ProposalStatus.BLOCKED
    assert out.blocked_reasons[0].code == "INTERNAL_ERROR"
    assert "boom" not in (out.blocked_reasons[0].message or "")
    record = ProposalsRepo(db_session).get(out.proposal_id)
    assert record is not None
    assert record.status is ProposalStatus.BLOCKED


@pytest.mark.usefixtures("seeded")
def test_losing_the_idempotency_race_reports_in_progress(db_session: Session) -> None:
    body = CreateProposalIn(customer_message="Can I pay later?", scenario_id="S01")
    ProposalsRepo(db_session).add_drafted(
        NewProposal(
            proposal_id="prop_winner00001",
            invoice_id="INV-001",
            idempotency_key="race-key-00001",
            request_hash=compute_request_hash("INV-001", body),
            customer_message="Can I pay later?",
            engine_version="1.0.0",
            currency="USD",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    agent = _SpyAgent(db_session)
    service = _service(db_session, agent, proposals=_BlindProposalsRepo(db_session))
    with pytest.raises(ConflictError) as caught:
        service.create_proposal("INV-001", body, "race-key-00001")

    assert caught.value.code == "IDEMPOTENCY_IN_PROGRESS"
    assert agent.in_transaction_during_run is None  # the loser never ran the agent


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize("key", ["", "has space", "ünïcode-key", "x" * 129, "line\nbreak"])
def test_invalid_idempotency_keys_are_rejected(db_session: Session, key: str) -> None:
    with pytest.raises(UnprocessableError) as caught:
        _service(db_session, _SpyAgent(db_session)).create_proposal(
            "INV-001", CreateProposalIn(customer_message="hello"), key
        )
    assert caught.value.code == "INVALID_IDEMPOTENCY_KEY"
