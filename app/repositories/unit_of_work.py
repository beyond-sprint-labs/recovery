"""Transaction boundary adapter.

Services own the transaction decisions (commit before every outbound call) but must not
import SQLAlchemy, so they talk to this thin adapter through a ``UnitOfWork`` protocol.
"""

from sqlalchemy.orm import Session


class SqlAlchemyUnitOfWork:
    """Commit/rollback of the request-scoped session shared by every repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
