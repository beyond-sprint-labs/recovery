import re

import pytest

from app.core.db import Base, get_engine, get_session_factory
from app.core.schemas import Actor, Severity
from app.repositories.audit_repo import AuditRepo
from app.services.audit_service import MAX_PAGE_LIMIT, AuditService

ENDPOINT = "/api/v1/audit-events"
SYSTEM = Actor(type="SYSTEM", id="recovery_service")
UTC_SECONDS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _seed(count: int, proposal_id: str | None = None) -> None:
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as session:
        service = AuditService(AuditRepo(session))
        for _ in range(count):
            service.record(
                actor=SYSTEM,
                action="PROPOSAL_DRAFTED",
                severity=Severity.INFO,
                summary="seeded event",
                proposal_id=proposal_id,
            )
        session.commit()


def test_empty_trail_returns_empty_page(client):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_seq": 0}


def test_incremental_polling_has_no_duplicates_and_no_gaps(client):
    _seed(5)

    first = client.get(ENDPOINT, params={"after_seq": 0, "limit": 3}).json()
    second = client.get(ENDPOINT, params={"after_seq": first["next_seq"], "limit": 3}).json()
    third = client.get(ENDPOINT, params={"after_seq": second["next_seq"], "limit": 3}).json()

    assert [e["seq"] for e in first["items"]] == [1, 2, 3]
    assert [e["seq"] for e in second["items"]] == [4, 5]
    assert third == {"items": [], "next_seq": 5}


def test_event_shape_matches_the_contract(client):
    _seed(1)

    event = client.get(ENDPOINT).json()["items"][0]

    assert event["event_id"] == "aud_000001"
    assert UTC_SECONDS.fullmatch(event["ts"])
    assert event["paypal_called"] is False
    assert event["actor"] == {"type": "SYSTEM", "id": "recovery_service", "mode": None}


def test_proposal_filter(client):
    _seed(2, proposal_id="prop_a")
    _seed(1, proposal_id="prop_b")

    body = client.get(ENDPOINT, params={"proposal_id": "prop_b"}).json()

    assert [e["seq"] for e in body["items"]] == [3]


@pytest.mark.parametrize(
    "params",
    [{"after_seq": -1}, {"limit": 0}, {"limit": MAX_PAGE_LIMIT + 1}, {"after_seq": "abc"}],
)
def test_invalid_query_returns_422_with_error_envelope(client, params):
    response = client.get(ENDPOINT, params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
