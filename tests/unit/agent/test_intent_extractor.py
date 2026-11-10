"""Unit tests for Recovery F1-06 intent extraction."""

import pytest

from app.agent.errors import AgentInputError, InvalidAgentOutputError
from app.agent.intent_extractor import extract_intent
from app.core.schemas import CustomerIntent


class FakeLLMClient:
    """Deterministic LLM replacement for tests."""

    def __init__(self, response: CustomerIntent):
        self.response = response
        self.last_schema = None

    def complete(self, system: str, user: str, schema: type):
        self.last_schema = schema
        return self.response


def test_extract_partial_payment():
    client = FakeLLMClient(
        CustomerIntent(
            available_now="300.00",
            preferred_installments=3,
        )
    )

    result = extract_intent(
        "I can pay $300 today in three installments.",
        client,
    )

    assert result.available_now == "300.00"
    assert result.preferred_installments == 3
    assert client.last_schema is CustomerIntent


def test_extract_discount():
    client = FakeLLMClient(CustomerIntent(requested_discount_pct="40"))

    result = extract_intent(
        "Can I get a 40% discount?",
        client,
    )

    assert result.requested_discount_pct == "40"


def test_missing_fields_are_not_invented():
    client = FakeLLMClient(CustomerIntent())

    result = extract_intent("Hello", client)

    assert result.available_now is None
    assert result.preferred_installments is None
    assert result.requested_discount_pct is None
    assert result.desired_date is None


def test_empty_message_is_rejected():
    client = FakeLLMClient(CustomerIntent())

    with pytest.raises(AgentInputError):
        extract_intent("   ", client)


def test_invalid_client_response_is_rejected():
    client = FakeLLMClient("invalid")

    with pytest.raises(InvalidAgentOutputError):
        extract_intent("I can pay today", client)


def test_extractor_receives_pre_sanitized_message():
    """The extractor forwards the server-sanitized message."""

    class CapturingClient(FakeLLMClient):
        def complete(self, system, user, schema):
            self.received_message = user
            return super().complete(system, user, schema)

    client = CapturingClient(CustomerIntent())

    extract_intent("Hello world", client)

    assert client.received_message == "Hello world"


def test_extractor_does_not_sanitize_internally():
    """Input sanitization belongs to RecoveryService."""

    class CapturingClient(FakeLLMClient):
        def complete(self, system, user, schema):
            self.received_message = user
            return super().complete(system, user, schema)

    client = CapturingClient(CustomerIntent())

    extract_intent("Hello   world", client)

    assert client.received_message == "Hello   world"


def test_intent_system_prompt_carries_the_output_contract():
    captured = {}

    class CapturingClient(FakeLLMClient):
        def complete(self, system, user, schema):
            captured["system"] = system
            return super().complete(system, user, schema)

    extract_intent("Hello", CapturingClient(CustomerIntent()))

    assert "No tools are available" in captured["system"]
    assert '"available_now"' in captured["system"]
