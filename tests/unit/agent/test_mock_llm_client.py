"""Tests for the deterministic Recovery mock LLM client."""

import pytest
from pydantic import BaseModel

from app.agent.mock_llm_client import MockLLMClient
from app.core.schemas import CustomerIntent


def test_mock_returns_predefined_intent():
    message = "I can pay $300 today."

    client = MockLLMClient(
        {
            message: CustomerIntent(available_now="300.00"),
        }
    )

    result = client.complete(
        system="Extract payment intent.",
        user=message,
        schema=CustomerIntent,
    )

    assert result.available_now == "300.00"


def test_mock_returns_empty_intent_for_unknown_message():
    client = MockLLMClient()

    result = client.complete(
        system="Extract payment intent.",
        user="Hello",
        schema=CustomerIntent,
    )

    assert result == CustomerIntent()


def test_mock_rejects_unsupported_schema():
    class UnknownResponse(BaseModel):
        value: str

    client = MockLLMClient()

    with pytest.raises(ValueError, match="Unsupported mock response schema"):
        client.complete(
            system="Test",
            user="Test",
            schema=UnknownResponse,
        )


def test_mock_response_is_independent_copy():
    message = "Can I get a 10% discount?"
    client = MockLLMClient(
        {
            message: CustomerIntent(requested_discount_pct="10"),
        }
    )

    first = client.complete("Extract intent", message, CustomerIntent)
    second = client.complete("Extract intent", message, CustomerIntent)

    assert first == second
    assert first is not second
