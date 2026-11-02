"""Dependency wiring (``Depends``) shared by routers."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session_factory


def get_db() -> Iterator[Session]:
    """Yield a database session and safely close it."""
    with get_session_factory()() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]
