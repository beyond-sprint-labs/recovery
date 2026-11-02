from pathlib import Path

from sqlalchemy import Engine

from app.core.db import build_engine, get_engine


def _pragma(engine: Engine, name: str) -> object:
    with engine.connect() as connection:
        return connection.exec_driver_sql(f"PRAGMA {name}").scalar_one()


def test_sqlite_engine_applies_wal_and_safety_pragmas(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'pragmas.db'}")

    assert _pragma(engine, "journal_mode") == "wal"
    assert _pragma(engine, "synchronous") == 1  # NORMAL
    assert _pragma(engine, "foreign_keys") == 1
    assert _pragma(engine, "busy_timeout") == 30_000  # 30 seconds
    engine.dispose()


def test_pragmas_apply_to_every_new_pooled_connection(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'pool.db'}")

    with engine.connect() as first, engine.connect() as second:
        for connection in (first, second):
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
    engine.dispose()


def test_cached_engine_uses_the_configured_database_url() -> None:
    assert _pragma(get_engine(), "journal_mode") == "wal"
