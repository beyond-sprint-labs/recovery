"""Shared fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import models as _models  # noqa: F401  (registers tables on Base)
from app.core.config import get_settings
from app.core.db import Base, get_engine, get_session_factory

TEST_ORIGIN = "http://localhost:5173"


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Isolate each test execution with a clean SQLite instance and deterministic settings."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYPAL_MODE", "mock")
    monkeypatch.setenv("AGENT_MODE", "scripted")
    monkeypatch.setenv("CORS_ORIGINS", TEST_ORIGIN)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    _clear_caches()
    yield
    get_engine().dispose()
    _clear_caches()


@pytest.fixture
def allowed_origin() -> str:
    return TEST_ORIGIN


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Session bound to the isolated test database with every table created."""
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as session:
        yield session
