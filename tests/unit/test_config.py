from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_production_with_mock_paypal_fails_fast() -> None:
    with pytest.raises(ValidationError, match="PAYPAL_MODE=mock"):
        Settings(_env_file=None, app_env="production", paypal_mode="mock", agent_mode="llm")


def test_production_with_scripted_agent_fails_fast() -> None:
    with pytest.raises(ValidationError, match="AGENT_MODE=scripted"):
        Settings(_env_file=None, app_env="production", paypal_mode="real", agent_mode="scripted")


def test_production_with_real_modes_starts() -> None:
    settings = Settings(
        _env_file=None, app_env="production", demo_mode=False, paypal_mode="real", agent_mode="llm"
    )
    assert settings.paypal_mode == "real"


def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="explicit origins"):
        Settings(_env_file=None, cors_origins="*")


def test_cors_origins_are_split_on_commas() -> None:
    settings = Settings(_env_file=None, cors_origins="http://a.test, http://b.test ,")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_policy_limits_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, policy_max_discount_pct=Decimal("101"))


def test_env_example_is_loadable_and_matches_the_roadmap_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)

    settings = Settings(_env_file=ENV_EXAMPLE)

    assert settings.demo_mode is True
    assert settings.paypal_mode == "mock"
    assert settings.agent_mode == "scripted"
    assert settings.allow_scenario_id is True
    assert settings.allow_sandbox_payment_shortcut is False
    assert settings.paypal_sandbox_buyer_email is None
    assert settings.uvicorn_workers == 1
    assert settings.policy_max_discount_pct == Decimal("15")
    assert settings.policy_max_financing_rate_pct == Decimal("2.0")
    assert settings.cors_origin_list == ["http://localhost:5173"]


def test_sandbox_buyer_email_is_validated_when_present() -> None:
    assert Settings(_env_file=None, paypal_sandbox_buyer_email="buyer@example.com")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, paypal_sandbox_buyer_email="not-an-email")
