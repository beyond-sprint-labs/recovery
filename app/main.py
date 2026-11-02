"""FastAPI entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import audit, customer, health, invoices, proposals, webhooks
from app.core.config import ENGINE_VERSION, get_settings
from app.core.db import Base, get_engine
from app.core.errors import register_exception_handlers

API_PREFIX: Final = "/api/v1"

CORS_ALLOWED_HEADERS: Final = ["Content-Type", "Idempotency-Key"]
CORS_ALLOWED_METHODS: Final = ["GET", "POST", "OPTIONS"]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(get_engine())
    yield


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(title="Recovery", version=ENGINE_VERSION, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=CORS_ALLOWED_HEADERS,
        max_age=600,
    )
    register_exception_handlers(app)

    app.include_router(health.router)
    for module in (invoices, proposals, customer, webhooks, audit):
        app.include_router(module.router, prefix=API_PREFIX)

    return app


app = create_app()
