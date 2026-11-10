"""Typed exceptions for the F1-06 negotiation agent."""


class AgentError(Exception):
    """Base exception for errors raised by the agent package."""


class InvalidAgentOutputError(AgentError):
    """The LLM or mock returned output that violates the contract."""


class AgentInputError(AgentError):
    """The agent received input it must refuse or cannot safely process."""


class LLMUnavailableError(AgentError):
    """The LLM provider cannot serve this request.

    The reason is a fixed, safe audit code:
    PROVIDER_UNAVAILABLE, PROVIDER_REJECTED, or BUDGET_EXHAUSTED.
    It must never contain credentials or customer information.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str = "PROVIDER_UNAVAILABLE",
    ) -> None:
        super().__init__(message)
        self.reason = reason
