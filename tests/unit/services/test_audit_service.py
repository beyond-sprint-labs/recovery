from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.core.errors import UnprocessableError
from app.core.schemas import Actor, AuditEvent, AuditEventsPage, RuleHit, Severity
from app.core.states import ProposalStatus
from app.repositories.audit_repo import AuditRepo
from app.services.audit_service import MAX_PAGE_LIMIT, SUMMARY_MAX_LENGTH, AuditService

FIXED_NOW = datetime(2026, 11, 2, 15, 4, 11, tzinfo=UTC)
SYSTEM = Actor(type="SYSTEM", id="recovery_service")


@pytest.fixture
def service(db_session: Session) -> AuditService:
    return AuditService(AuditRepo(db_session), clock=lambda: FIXED_NOW)


def _record(service: AuditService, **overrides: object) -> AuditEvent:
    values: dict[str, object] = {
        "actor": SYSTEM,
        "action": "PROPOSAL_DRAFTED",
        "severity": Severity.INFO,
        "summary": "2 alternatives drafted within policy; awaiting merchant approval",
    }
    values.update(overrides)
    return service.record(**values)  # type: ignore[arg-type]


def _read(after_seq: int = 0, limit: int = 100, proposal_id: str | None = None) -> AuditEventsPage:
    """Read through a brand-new session so nothing comes from the identity map."""
    with get_session_factory()() as session:
        return AuditService(AuditRepo(session)).list_events(
            after_seq=after_seq, limit=limit, proposal_id=proposal_id
        )


def test_record_assigns_monotonic_seq_and_padded_event_id(service):
    events = [_record(service) for _ in range(3)]

    assert [e.seq for e in events] == [1, 2, 3]
    assert [e.event_id for e in events] == ["aud_000001", "aud_000002", "aud_000003"]


def test_blocked_event_round_trips_the_contract(service, db_session):
    rule = RuleHit(code="MAX_DISCOUNT_PCT", limit="15", attempted="40", unit="pct")
    agent = Actor(type="AGENT", id="agent_v1", mode="DEMO")
    _record(
        service,
        actor=Actor(type="SYSTEM", id="policy_engine"),
        action="PROPOSAL_BLOCKED",
        severity=Severity.CRITICAL,
        invoice_id="INV-001",
        proposal_id="prop_c41d02",
        state_from=ProposalStatus.DRAFTED,
        state_to=ProposalStatus.BLOCKED,
        rule=rule,
        proposed_by=agent,
        summary="AI-proposed 40% settlement discount exceeds merchant limit of 15%",
    )
    db_session.commit()

    event = _read().items[0]

    assert event.action == "PROPOSAL_BLOCKED"
    assert event.severity is Severity.CRITICAL
    assert event.state_from is ProposalStatus.DRAFTED
    assert event.state_to is ProposalStatus.BLOCKED
    assert event.rule == rule
    assert event.proposed_by == agent
    assert event.paypal_called is False
    assert event.actor == Actor(type="SYSTEM", id="policy_engine")


def test_timestamp_is_utc_aware_and_serialised_without_microseconds(service, db_session):
    _record(service)
    db_session.commit()

    page = _read()

    assert page.items[0].ts == FIXED_NOW
    assert page.items[0].ts.tzinfo is not None
    assert page.model_dump(mode="json")["items"][0]["ts"] == "2026-11-02T15:04:11Z"


def test_optional_source_and_paypal_ref_are_persisted(service, db_session):
    _record(
        service,
        action="PAYPAL_INVOICE_SENT",
        source="RECONCILIATION",
        paypal_ref="INV2-REAL-123",
        paypal_called=True,
    )
    db_session.commit()

    event = _read().items[0]

    assert event.source == "RECONCILIATION"
    assert event.paypal_ref == "INV2-REAL-123"
    assert event.paypal_called is True


def test_record_does_not_commit(service, db_session):
    _record(service)
    db_session.rollback()

    assert _read().items == []


def test_summary_is_truncated_to_the_column_limit(service):
    event = _record(service, summary="x" * (SUMMARY_MAX_LENGTH + 50))

    assert len(event.summary) == SUMMARY_MAX_LENGTH


def test_list_events_is_ascending_and_respects_the_cursor(service, db_session):
    for _ in range(5):
        _record(service)
    db_session.commit()

    first = _read(after_seq=0, limit=3)
    second = _read(after_seq=first.next_seq, limit=3)
    drained = _read(after_seq=second.next_seq, limit=3)

    assert [e.seq for e in first.items] == [1, 2, 3]
    assert first.next_seq == 3
    assert [e.seq for e in second.items] == [4, 5]
    assert second.next_seq == 5
    assert drained.items == []
    assert drained.next_seq == 5


def test_empty_trail_keeps_the_cursor_at_zero():
    # No events and no fixture-created tables needed beyond the session factory.
    from app.core.db import Base, get_engine

    Base.metadata.create_all(get_engine())

    page = _read()

    assert (page.items, page.next_seq) == ([], 0)


def test_list_events_filters_by_proposal(service, db_session):
    _record(service, proposal_id="prop_a")
    _record(service, proposal_id="prop_b")
    _record(service, proposal_id="prop_a")
    db_session.commit()

    page = _read(proposal_id="prop_a")

    assert [e.seq for e in page.items] == [1, 3]
    assert page.next_seq == 3


@pytest.mark.parametrize(
    ("after_seq", "limit"),
    [(-1, 10), (0, 0), (0, MAX_PAGE_LIMIT + 1)],
)
def test_invalid_pagination_is_rejected(service, after_seq, limit):
    with pytest.raises(UnprocessableError) as exc:
        service.list_events(after_seq=after_seq, limit=limit, proposal_id=None)

    assert exc.value.code == "INVALID_PAGINATION"


def test_serialised_event_exposes_only_schema_fields(service, db_session):
    _record(service)
    db_session.commit()

    dumped = _read().model_dump(mode="json")["items"][0]

    assert set(dumped) == set(AuditEvent.model_fields)
