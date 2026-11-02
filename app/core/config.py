"""Application settings.

Loaded once from environment variables (and an optional ``.env`` file).
``DEMO_MODE=true`` is a preset: safe defaults apply when not explicitly defined.
``APP_ENV=production`` fails fast if any mock mode remains active.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Final, Literal, Self

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENGINE_VERSION: Final = "1.0.0"

PercentValue = Annotated[Decimal, Field(ge=0, le=100)]


class Settings(BaseSettings):
    """Typed view over the process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # --- runtime modes -----------------------------------------------------
    app_env: Literal["local", "test", "production"] = "local"
    demo_mode: bool = True
    paypal_mode: Literal["mock", "real"] = "mock"
    agent_mode: Literal["scripted", "llm"] = "scripted"
    allow_scenario_id: bool = True
    allow_sandbox_payment_shortcut: bool = False
    customer_token_ttl_min: Annotated[int, Field(ge=1, le=10_080)] = 1_440

    # --- infrastructure ----------------------------------------------------
    database_url: str = "sqlite:///./recovery.db"
    public_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173"
    uvicorn_workers: Annotated[int, Field(ge=1, le=2)] = 1

    # --- LLM ---------------------------------------------------------------
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")

    # --- PayPal ------------------------------------------------------------
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_client_id: str = ""
    paypal_client_secret: SecretStr = SecretStr("")
    paypal_webhook_id: str = ""
    paypal_sandbox_buyer_email: EmailStr | None = None

    # --- merchant policy (server-side only, never accepted from request) ---
    policy_max_discount_pct: PercentValue = Decimal("15")
    policy_min_down_payment_pct: PercentValue = Decimal("20")
    policy_max_installments: Annotated[int, Field(ge=1, le=120)] = 6
    policy_max_financing_rate_pct: PercentValue = Decimal("2.0")
    merchant_discount_rate_pct: PercentValue = Decimal("1.0")

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: str) -> str:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is forbidden")
        return value

    @model_validator(mode="after")
    def _enforce_production_guards(self) -> Self:
        if self.app_env != "production":
            return self
        problems: list[str] = []
        if self.paypal_mode == "mock":
            problems.append("PAYPAL_MODE=mock is forbidden when APP_ENV=production")
        if self.agent_mode == "scripted":
            problems.append("AGENT_MODE=scripted is forbidden when APP_ENV=production")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed, de-blanked list of allowed browser origins."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
