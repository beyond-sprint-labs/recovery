from itertools import pairwise

import pytest

from app.core.states import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    InvalidTransitionError,
    ProposalStatus,
    assert_transition,
)

# Independent copy of the ROADMAP section 4.5 table. Do NOT import it from app.core.states.
EXPECTED: dict[str, set[str]] = {
    "DRAFTED": {"PENDING_MERCHANT", "BLOCKED"},
    "PENDING_MERCHANT": {"APPROVED", "REJECTED", "BLOCKED"},
    "APPROVED": {"PENDING_CUSTOMER"},
    "PENDING_CUSTOMER": {"ACCEPTED", "DECLINED", "EXPIRED"},
    "ACCEPTED": {"EXECUTING"},
    "EXECUTING": {"EXECUTED", "FAILED", "NEEDS_RECONCILIATION"},
    "EXECUTED": {"PAID"},
    "NEEDS_RECONCILIATION": {"EXECUTED", "FAILED"},
    "PAID": set(),
    "BLOCKED": set(),
    "REJECTED": set(),
    "DECLINED": set(),
    "EXPIRED": set(),
    "FAILED": set(),
}
ALL_STATES = sorted(EXPECTED)


def test_enum_matches_the_documented_states_exactly() -> None:
    assert {status.value for status in ProposalStatus} == set(EXPECTED)
    assert len(ProposalStatus) == 14


def test_there_is_no_partially_paid_state_in_phase_1() -> None:
    assert "PARTIALLY_PAID" not in {status.value for status in ProposalStatus}


def test_every_state_has_an_entry_in_the_transition_table() -> None:
    assert {status.value for status in ALLOWED_TRANSITIONS} == set(EXPECTED)


@pytest.mark.parametrize("source", ALL_STATES)
@pytest.mark.parametrize("target", ALL_STATES)
def test_full_transition_matrix(source: str, target: str) -> None:
    if target in EXPECTED[source]:
        assert_transition(source, target)
        return
    with pytest.raises(InvalidTransitionError) as excinfo:
        assert_transition(source, target)
    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "INVALID_TRANSITION"
    assert (excinfo.value.from_state, excinfo.value.to_state) == (source, target)


def test_terminal_states_are_derived_from_the_table() -> None:
    expected_terminal = {state for state, targets in EXPECTED.items() if not targets}
    assert {status.value for status in TERMINAL_STATES} == expected_terminal
    assert expected_terminal == {"PAID", "BLOCKED", "REJECTED", "DECLINED", "EXPIRED", "FAILED"}


@pytest.mark.parametrize(
    "pair", [("DRAFTED", "NOPE"), ("NOPE", "PAID"), ("", ""), ("paid", "PAID")]
)
def test_unknown_state_names_are_invalid_transitions_not_crashes(pair: tuple[str, str]) -> None:
    with pytest.raises(InvalidTransitionError):
        assert_transition(*pair)


def test_happy_path_walks_from_drafted_to_paid() -> None:
    path = [
        "DRAFTED",
        "PENDING_MERCHANT",
        "APPROVED",
        "PENDING_CUSTOMER",
        "ACCEPTED",
        "EXECUTING",
        "EXECUTED",
        "PAID",
    ]
    for source, target in pairwise(path):
        assert_transition(source, target)


def test_needs_reconciliation_never_goes_back_to_executing() -> None:
    # The original invoice is already cancelled: reconcile may only retry the send.
    with pytest.raises(InvalidTransitionError):
        assert_transition(ProposalStatus.NEEDS_RECONCILIATION, ProposalStatus.EXECUTING)
