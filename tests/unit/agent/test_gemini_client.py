"""HTTP regression tests for the Gemini provider (F1-20)."""

import json

import httpx
import pytest
import respx

from app.agent.errors import InvalidAgentOutputError, LLMUnavailableError
from app.agent.gemini_client import GeminiClient
from app.core.config import Settings
from app.core.schemas import CustomerIntent

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        llm_provider="gemini",
        llm_model="gemini-test",
        llm_api_key="fake-test-key",
    )


def gemini_response(text):
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
    )


@respx.mock
def test_structured_intent(settings):
    route = respx.post(URL).mock(
        return_value=gemini_response(json.dumps({"preferred_installments": 3}))
    )

    with httpx.Client() as http:
        client = GeminiClient(settings, client=http)
        result = client.complete(
            system="Extract intent",
            user="Can I pay in three installments?",
            schema=CustomerIntent,
        )

    assert result.preferred_installments == 3
    assert route.call_count == 1

    request = route.calls[0].request
    assert request.headers["x-goog-api-key"] == "fake-test-key"
    assert "fake-test-key" not in str(request.url)

    payload = json.loads(request.content)
    assert payload["generationConfig"]["temperature"] == 0
    assert payload["generationConfig"]["responseMimeType"] == "application/json"


@respx.mock
def test_text_generation(settings):
    respx.post(URL).mock(return_value=gemini_response("The approved payment plan is available."))

    with httpx.Client() as http:
        client = GeminiClient(settings, client=http)
        result = client.generate_text(
            system="Write an explanation",
            user="Approved financial context",
        )

    assert result == "The approved payment plan is available."


@respx.mock
def test_one_retry_after_server_error(settings):
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(503),
            gemini_response("{}"),
        ]
    )

    with httpx.Client() as http:
        client = GeminiClient(settings, client=http)
        result = client.complete("System", "Message", CustomerIntent)

    assert result == CustomerIntent()
    assert route.call_count == 2


@pytest.mark.parametrize("status", [429, 500, 503])
@respx.mock
def test_retry_limit_for_temporary_http_failures(settings, status):
    route = respx.post(URL).mock(return_value=httpx.Response(status))

    with httpx.Client() as http:
        client = GeminiClient(settings, client=http)

        with pytest.raises(LLMUnavailableError):
            client.complete("System", "Message", CustomerIntent)

    assert route.call_count == 2


@respx.mock
def test_timeout_is_reported_without_network(settings):
    route = respx.post(URL).mock(side_effect=httpx.ReadTimeout("Simulated timeout"))

    with httpx.Client() as http:
        client = GeminiClient(settings, client=http)

        with pytest.raises(LLMUnavailableError):
            client.complete("System", "Message", CustomerIntent)

    assert route.call_count == 2


@respx.mock
def test_invalid_http_json_is_rejected(settings):
    respx.post(URL).mock(return_value=httpx.Response(200, text="not-json"))

    with httpx.Client() as http:
        client = GeminiClient(settings, client=http)

        with pytest.raises(InvalidAgentOutputError):
            client.complete("System", "Message", CustomerIntent)


@respx.mock
def test_invalid_pydantic_output_is_rejected(settings):
    respx.post(URL).mock(return_value=gemini_response('{"requested_discount_pct": "150"}'))

    with httpx.Client() as http:
        client = GeminiClient(settings, client=http)

        with pytest.raises(InvalidAgentOutputError):
            client.complete("System", "Message", CustomerIntent)


def test_missing_key_is_rejected():
    settings = Settings(
        _env_file=None,
        llm_provider="gemini",
        llm_model="gemini-test",
        llm_api_key="",
    )

    with pytest.raises(ValueError, match="Missing LLM API key"):
        GeminiClient(settings)
