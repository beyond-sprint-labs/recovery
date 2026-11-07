"""Typed exceptions for the F1-06 negotiation agent."""


class AgentError(Exception):
    """Base exception for errors raised by the agent package."""


class InvalidAgentOutputError(AgentError):
    """The LLM or mock returned output that violates the contract."""


class AgentInputError(AgentError):
    """The agent received input it must refuse or cannot safely process."""
