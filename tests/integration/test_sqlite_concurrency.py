"""F1-16 DoD: UI polling pattern (1 writer + 5 readers) never hits 'database is locked'.

Duration defaults to 30 s as required by the card. Override locally with
AUDIT_CONCURRENCY_SECONDS=5 for a quick run.
"""

import os
import threading
import time

from app.core.db import Base, get_engine, get_session_factory
from app.core.schemas import Actor, Severity
from app.repositories.audit_repo import AuditRepo
from app.services.audit_service import AuditService

DURATION_SECONDS = float(os.environ.get("AUDIT_CONCURRENCY_SECONDS", "30"))
READERS = 5
POLL_INTERVAL_SECONDS = 1.0
WRITE_INTERVAL_SECONDS = 0.05
SYSTEM = Actor(type="SYSTEM", id="recovery_service")


def _write_one() -> None:
    with get_session_factory()() as session:
        AuditService(AuditRepo(session)).record(
            actor=SYSTEM,
            action="PROPOSAL_DRAFTED",
            severity=Severity.INFO,
            summary="concurrency probe",
        )
        session.commit()


def _drain(seen: list[int], cursor: int) -> int:
    """Read every page after ``cursor`` and return the new cursor."""
    while True:
        with get_session_factory()() as session:
            page = AuditService(AuditRepo(session)).list_events(
                after_seq=cursor, limit=500, proposal_id=None
            )
        if not page.items:
            return cursor
        seen.extend(event.seq for event in page.items)
        cursor = page.next_seq


def test_one_writer_and_five_polling_readers_never_lock():
    Base.metadata.create_all(get_engine())
    writer_done = threading.Event()
    errors: list[BaseException] = []
    written = 0
    seen_by_reader: list[list[int]] = [[] for _ in range(READERS)]

    def writer() -> None:
        nonlocal written
        try:
            deadline = time.monotonic() + DURATION_SECONDS
            while time.monotonic() < deadline:
                _write_one()
                written += 1
                time.sleep(WRITE_INTERVAL_SECONDS)
        except BaseException as exc:
            errors.append(exc)
        finally:
            writer_done.set()

    def reader(seen: list[int]) -> None:
        cursor = 0
        try:
            while True:
                finished = writer_done.is_set()
                cursor = _drain(seen, cursor)
                if finished:
                    return
                writer_done.wait(POLL_INTERVAL_SECONDS)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, name="writer")]
    threads += [
        threading.Thread(target=reader, args=(seen,), name=f"reader-{i}")
        for i, seen in enumerate(seen_by_reader)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=DURATION_SECONDS + 30)

    assert errors == []
    assert written > 0
    expected = list(range(1, written + 1))
    for seen in seen_by_reader:
        assert seen == expected
