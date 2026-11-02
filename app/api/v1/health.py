"""Liveness and configuration probe. Mounted at ``/health`` (outside ``/api/v1``)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import ENGINE_VERSION
from app.core.deps import SettingsDep

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: Literal["ok"]
    demo_mode: bool
    engine_version: str
    paypal_mode: Literal["mock", "real"] | None = None
    agent_mode: Literal["scripted", "llm"] | None = None


@router.get("/health", response_model=HealthOut)
def read_health(settings: SettingsDep) -> HealthOut:
    return HealthOut(
        status="ok",
        demo_mode=settings.demo_mode,
        engine_version=ENGINE_VERSION,
        paypal_mode=settings.paypal_mode,
        agent_mode=settings.agent_mode,
    )