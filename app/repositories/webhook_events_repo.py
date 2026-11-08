"""Data access for webhook events. No business rules live here."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models import WebhookEventRow


class WebhookEventsRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def register(self, event_id: str, event_type: str) -> bool:
        """Register an event. Returns False if it was already processed (duplicate).

        The ``event_id`` PRIMARY KEY is the real defence (DEC-09). We flush to hit the
        constraint immediately, but we never commit here: the caller owns the transaction.
        """
        row = WebhookEventRow(
            event_id=event_id,
            event_type=event_type,
            received_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self._session.add(row)
        try:
            self._session.flush()
            return True
        except IntegrityError:
            self._session.rollback()
            return False
