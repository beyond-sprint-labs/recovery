"""Proposal lifecycle: states, allowed transitions and the transition guard.

Single source of truth for the state machine. Services must call
``assert_transition`` before every compare-and-set UPDATE of ``proposals.status``.
"""

from enum import StrEnum
from typing import Final

from app.core.errors import ConflictError


class ProposalStatus(StrEnum):
    DRAFTED = "DRAFTED"
    BLOCKED = "BLOCKED"
    PENDING_MERCHANT = "PENDING_MERCHANT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING_CUSTOMER = "PENDING_CUSTOMER"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    # Alternative 2 (installments): PAID means "first scheduled payment confirmed".
    # There is deliberately no PARTIALLY_PAID state in Phase 1 (DEC-29).
    PAID = "PAID"


_S = ProposalStatus

ALLOWED_TRANSITIONS: Final[dict[ProposalStatus, frozenset[ProposalStatus]]] = {
    _S.DRAFTED: frozenset({_S.PENDING_MERCHANT, _S.BLOCKED}),
    _S.PENDING_MERCHANT: frozenset({_S.APPROVED, _S.REJECTED}),
    _S.APPROVED: frozenset({_S.PENDING_CUSTOMER}),
    _S.PENDING_CUSTOMER: frozenset({_S.ACCEPTED, _S.DECLINED, _S.EXPIRED}),
    _S.ACCEPTED: frozenset({_S.EXECUTING}),
    _S.EXECUTING: frozenset({_S.EXECUTED, _S.FAILED, _S.NEEDS_RECONCILIATION}),
    _S.EXECUTED: frozenset({_S.PAID}),
    _S.NEEDS_RECONCILIATION: frozenset({_S.EXECUTED, _S.FAILED}),
    _S.PAID: frozenset(),
    _S.BLOCKED: frozenset(),
    _S.REJECTED: frozenset(),
    _S.DECLINED: frozenset(),
    _S.EXPIRED: frozenset(),
    _S.FAILED: frozenset(),
}

TERMINAL_STATES: Final[frozenset[ProposalStatus]] = frozenset(
    status for status, targets in ALLOWED_TRANSITIONS.items() if not targets
)


class InvalidTransitionError(ConflictError):
    """Raised for any transition outside the table. Maps to HTTP 409."""

    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(
            "INVALID_TRANSITION", f"Cannot move proposal from {from_state} to {to_state}"
        )
        self.from_state = from_state
        self.to_state = to_state


def assert_transition(from_state: ProposalStatus | str, to_state: ProposalStatus | str) -> None:
    """Raise ``InvalidTransitionError`` unless ``from_state -> to_state`` is allowed.

    Accepts plain strings so values read straight from the database can be checked.
    Unknown state names are invalid transitions, never a crash.
    """
    try:
        source, target = ProposalStatus(from_state), ProposalStatus(to_state)
    except ValueError as exc:
        raise InvalidTransitionError(str(from_state), str(to_state)) from exc
    if target not in ALLOWED_TRANSITIONS[source]:
        raise InvalidTransitionError(source.value, target.value)
