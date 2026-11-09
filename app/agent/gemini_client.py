"""Gemini REST client for structured intent and text generation."""

import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.agent.errors import InvalidAgentOutputError, LLMUnavailableError
from app.agent.llm_client import ResponseT
from app.core.config import Settings

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
_MODEL_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]*")


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

    def _request(
        self,
        system: str,
        user: str,
        *,
        json_output: bool,
    ) -> str:
        config: dict[str, Any] = {
            "temperature": 0,
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

        for attempt in range(2):
            try:
                if self._client is None:
                    with httpx.Client(timeout=8.0) as client:
                        response = client.post(
                            url,
                            headers=headers,
                            json=payload,
                        )
                else:
                    response = self._client.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=8.0,
                    )
            except httpx.RequestError:
                if attempt == 0:
                    continue
                raise LLMUnavailableError("LLM provider transport unavailable") from None

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 0:
                    continue
                raise LLMUnavailableError("LLM provider temporarily unavailable")

            if not 200 <= response.status_code < 300:
                raise LLMUnavailableError("LLM provider request rejected")

            try:
                body = response.json()
                parts = body["candidates"][0]["content"]["parts"]
                text = "".join(part["text"] for part in parts)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                raise InvalidAgentOutputError("LLM response has an invalid structure") from None

            if not text.strip():
                raise InvalidAgentOutputError("LLM returned an empty response")

            return text

        raise LLMUnavailableError("LLM provider unavailable")

    def complete(
        self,
        system: str,
        user: str,
        schema: type[ResponseT],
    ) -> ResponseT:
        """Validate model JSON against the requested Pydantic schema."""
        text = self._request(system, user, json_output=True)

        try:
            return schema.model_validate_json(text)
        except ValidationError:
            raise InvalidAgentOutputError("LLM structured output failed validation") from None

    def generate_text(self, system: str, user: str) -> str:
        """Generate an untrusted draft for backend Text Guard."""
        return self._request(system, user, json_output=False)
