"""Deterministic mock LLM client for Recovery F1-06."""

from collections.abc import Mapping
from typing import cast

from app.agent.llm_client import ResponseT
from app.core.schemas import CustomerIntent


class MockLLMClient:
    """Return predefined structured responses without API calls."""

    def __init__(
        self,
        responses: Mapping[str, CustomerIntent] | None = None,
    ):
        self.responses = dict(responses or {})

    def complete(
        self,
        system: str,
        user: str,
        schema: type[ResponseT],
    ) -> ResponseT:
        """Return a predefined response matching the requested schema."""

        if schema is not CustomerIntent:
            raise ValueError("Unsupported mock response schema")

        intent = self.responses.get(user)

        if intent is None:
            return cast(ResponseT, CustomerIntent())

        return cast(ResponseT, intent.model_copy(deep=True))
