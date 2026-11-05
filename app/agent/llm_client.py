"""LLM client contract for Recovery F1-06."""

from typing import Protocol, TypeVar

from pydantic import BaseModel

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class LLMClient(Protocol):
    """Interface for structured LLM responses."""

    def complete(
        self,
        system: str,
        user: str,
        schema: type[ResponseT],
    ) -> ResponseT:
        """Return a response validated against the schema."""
        ...
