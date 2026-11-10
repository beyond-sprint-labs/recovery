"""Gemini REST client for structured intent and text generation."""

import html
import re
import time
from typing import Any, Final

import httpx
from pydantic import ValidationError

from app.agent.errors import InvalidAgentOutputError, LLMUnavailableError
from app.agent.llm_client import ResponseT
from app.core.config import Settings

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
_MODEL_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]*")
_MAX_ATTEMPTS: Final = 2
_RETRY_DELAY_SECONDS: Final = 0.25
_JSON_MAX_TOKENS: Final = 256
_TEXT_MAX_TOKENS: Final = 512
_MAX_RESPONSE_CHARS: Final = 2_000


class GeminiClient:
    """Implement LLMClient and TextLLMClient using HTTP only."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        if settings.llm_provider != "gemini":
            raise ValueError("Unsupported LLM provider")

        if not _MODEL_PATTERN.fullmatch(settings.llm_model):
            raise ValueError("Invalid LLM model configuration")

        api_key = settings.llm_api_key.get_secret_value()
        if not api_key:
            raise ValueError("Missing LLM API key")

        self._model = settings.llm_model
        self._api_key = api_key
        self._client = client

    def _post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        """Send one HTTP request with an eight-second timeout."""
        if self._client is None:
            with httpx.Client(timeout=8.0) as client:
                return client.post(url, headers=headers, json=payload)

        return self._client.post(
            url,
            headers=headers,
            json=payload,
            timeout=8.0,
        )

    def _send(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        """Retry only temporary transport and provider failures."""
        for attempt in range(_MAX_ATTEMPTS):
            if attempt:
                time.sleep(_RETRY_DELAY_SECONDS)

            try:
                response = self._post(url, headers, payload)
            except httpx.RequestError:
                continue

            if response.status_code == 429 or response.status_code >= 500:
                continue

            return response

        raise LLMUnavailableError("LLM provider temporarily unavailable")

    def _request(
        self,
        system: str,
        user: str,
        *,
        json_output: bool,
    ) -> str:
        config: dict[str, Any] = {
            "temperature": 0,
            "maxOutputTokens": _JSON_MAX_TOKENS if json_output else _TEXT_MAX_TOKENS,
        }
        if json_output:
            config["responseMimeType"] = "application/json"

        payload = {
            "systemInstruction": {
                "parts": [{"text": system}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user}],
                }
            ],
            "generationConfig": config,
        }

        url = f"{_API_ROOT}/{self._model}:generateContent"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        response = self._send(url, headers, payload)

        if not 200 <= response.status_code < 300:
            raise LLMUnavailableError(
                "LLM provider rejected the request",
                reason="PROVIDER_REJECTED",
            )

        try:
            body = response.json()
            parts = body["candidates"][0]["content"]["parts"]
            text = "".join(part["text"] for part in parts)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise InvalidAgentOutputError("LLM response has an invalid structure") from None

        if not text.strip():
            raise InvalidAgentOutputError("LLM returned an empty response")

        if len(text) > _MAX_RESPONSE_CHARS:
            raise InvalidAgentOutputError("LLM response exceeds the allowed length")

        return text

    def complete(
        self,
        system: str,
        user: str,
        schema: type[ResponseT],
    ) -> ResponseT:
        """Validate model JSON against the requested Pydantic schema."""
        delimited = f"<customer_message>{html.escape(user, quote=False)}</customer_message>"
        text = self._request(system, delimited, json_output=True)

        try:
            return schema.model_validate_json(text)
        except ValidationError:
            raise InvalidAgentOutputError("LLM structured output failed validation") from None

    def generate_text(self, system: str, user: str) -> str:
        """Generate an untrusted draft for backend Text Guard."""
        return self._request(system, user, json_output=False)
