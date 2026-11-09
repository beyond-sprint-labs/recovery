"""Data access for webhook events. No business rules live here."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models import WebhookEventRow


class WebhookEventsRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def register(self, event_id: str, event_type: str) -> bool:
        """Register an event. Returns False if it was already processed.

        Uses a SAVEPOINT so the caller retains transaction ownership.
        """
        row = WebhookEventRow(
            event_id=event_id,
            event_type=event_type[:64],
            received_at=datetime.now(UTC),
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
                return True
        except IntegrityError:
            return False
