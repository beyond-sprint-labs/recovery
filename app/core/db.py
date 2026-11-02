"""SQLAlchemy engine and session factory.

SQLite is hardened for a UI polling pattern: WAL mode allows concurrent readers
with a single writer, busy timeout absorbs transient locks, and foreign keys are enforced.
"""

import sqlite3
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def build_engine(database_url: str) -> Engine:
    """Create an engine; apply SQLite hardening only for SQLite URLs."""
    if not database_url.startswith("sqlite"):
        return create_engine(database_url, pool_pre_ping=True)

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _apply_sqlite_pragmas(
        dbapi_connection: sqlite3.Connection,
        _connection_record: ConnectionPoolEntry,
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
        finally:
            cursor.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide engine built from settings (cached)."""
    return build_engine(get_settings().database_url)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory (cached)."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)