from typing import Protocol, Type
from pydantic import BaseModel


class LLMClient(Protocol):

    # Interface to interact with the LLM provider (OpenAI, Anthropic, etc.).

    def complete(self, system: str, user: str, schema: Type[BaseModel]) -> BaseModel:
        # Sends a prompt and expects a JSON validated by the Pydantic schema.
        ...
