"""F1-20 tests for provider selection and safe demo mode."""

import pytest

from app.agent.fallback_agent import FallbackAgent
from app.agent.mock_agent import ScriptedAgent
from app.core.config import Settings
from app.core.deps import get_agent_factory
from app.core.errors import UpstreamError


def settings(**overrides):
    defaults = {
        "_env_file": None,
        "app_env": "test",
        "demo_mode": False,
        "agent_mode": "llm",
        "llm_provider": "gemini",
        "llm_model": "gemini-test",
        "llm_api_key": "fake-test-key",
    }
    return Settings(**(defaults | overrides))


def test_demo_mode_without_api_key():
    factory = get_agent_factory(
        settings(demo_mode=True, llm_api_key="", llm_provider="", llm_model="")
    )

    binding = factory(None)

    assert isinstance(binding.agent, ScriptedAgent)
    assert binding.mode == "DEMO"


def test_scripted_mode_without_api_key():
    factory = get_agent_factory(
        settings(agent_mode="scripted", llm_api_key="", llm_provider="", llm_model="")
    )

    binding = factory("S01")

    assert isinstance(binding.agent, ScriptedAgent)
    assert binding.mode == "DEMO"


def test_llm_mode_builds_fallback_agent():
    binding = get_agent_factory(settings())(None)

    assert isinstance(binding.agent, FallbackAgent)
    assert binding.mode == "LLM"


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_provider": ""},
        {"llm_provider": "unsupported"},
        {"llm_model": ""},
        {"llm_api_key": ""},
    ],
)
def test_invalid_llm_configuration_is_rejected(overrides):
    factory = get_agent_factory(settings(**overrides))

    with pytest.raises(UpstreamError):
        factory(None)


def test_fastapi_startup_rejects_missing_llm_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject incomplete LLM configuration during application startup."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    configured = settings(llm_api_key="")

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: configured,
    )

    with (
        pytest.raises(UpstreamError, match="LLM configuration is incomplete"),
        TestClient(create_app()),
    ):
        pass


def test_fastapi_demo_startup_without_llm_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Demo mode starts without LLM credentials or network access."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    configured = settings(
        demo_mode=True,
        llm_api_key="",
        llm_provider="",
        llm_model="",
    )

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: configured,
    )

    with TestClient(create_app()) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200


def test_production_rejects_demo_mode():
    """Production must never silently select the scripted demo agent."""
    with pytest.raises(ValueError, match="DEMO_MODE=true"):
        settings(
            app_env="production",
            demo_mode=True,
            paypal_mode="real",
            agent_mode="llm",
        )
