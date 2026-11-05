"""Deterministic mock LLM client for Recovery F1-06."""

from collections.abc import Mapping

from pydantic import BaseModel

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
        schema: type[BaseModel],
    ) -> BaseModel:
        """Return a predefined response matching the requested schema."""

        if schema is not CustomerIntent:
            raise ValueError("Unsupported mock response schema")

        intent = self.responses.get(user)

        if intent is None:
            return CustomerIntent()

        return intent.model_copy(deep=True)
