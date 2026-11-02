import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.schemas import (
    AuditEvent,
    CreateProposalIn,
    Installments,
    Money,
    Pct,
    SignedMoney,
)

MONEY = TypeAdapter(Money)
SIGNED_MONEY = TypeAdapter(SignedMoney)
PCT = TypeAdapter(Pct)
INSTALLMENTS = TypeAdapter(Installments)


@pytest.mark.parametrize("value", ["0.00", "0.01", "900.00", "1021.10", "999999999999.99"])
def test_money_accepts_canonical_amounts(value: str) -> None:
    assert MONEY.validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "900.0",  # one decimal
        "900.000",  # three decimals
        "900",  # no decimals
        "9e2",  # exponent
        "-1.00",  # negative
        "+1.00",
        "",
        "0900.00",  # leading zero
        "1000000000000.00",  # 13 integer digits
        " 900.00",
        "900.00 ",
        "900.00\n",
        "\uff19\uff10\uff10.\uff10\uff10",  # full-width digits must not pass
        "\u0669\u0660\u0660.\u0660\u0660",  # Arabic-Indic digits must not pass
        "9\u0660\u0660.\u0660\u0660",  # ASCII lead + Arabic-Indic: a naive digit class accepts this
        "9\uff10\uff10.00",  # ASCII lead + full-width digits
        "900.\uff10\uff10",  # Unicode decimals only
        900,  # numbers are never money
        900.0,
    ],
)
def test_money_rejects_everything_else(value: object) -> None:
    with pytest.raises(ValidationError):
        MONEY.validate_python(value)


@pytest.mark.parametrize("value", ["-100.00", "6.91", "0.00", "-0.01", "-400.00"])
def test_signed_money_accepts_differences(value: str) -> None:
    assert SIGNED_MONEY.validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "-100",
        "--1.00",
        "+1.00",
        "-0900.00",
        "",
        "1e2",
        "-\uff19.\uff10\uff10",
        "-9\u0660.\u0660\u0660",
    ],
)
def test_signed_money_rejects_malformed(value: str) -> None:
    with pytest.raises(ValidationError):
        SIGNED_MONEY.validate_python(value)


@pytest.mark.parametrize(
    "value", ["0", "10", "10.5", "10.50", "1.5", "2.0", "99.9999", "100", "100.0", "0.5"]
)
def test_pct_accepts_values_between_0_and_100(value: str) -> None:
    assert PCT.validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "101",
        "100.5",
        "100.0001",
        "-5",
        "",
        "1e1",
        "010",
        " 10",
        "10 ",
        "10.",
        ".5",
        "1.23456",
        "\uff11\uff10",  # full-width digits
        "1\uff10",  # ASCII lead + full-width digit
        "10.\uff15",  # Unicode decimals
        "NaN",
        "Infinity",
        10,
        10.5,
    ],
)
def test_pct_rejects_out_of_range_or_malformed(value: object) -> None:
    with pytest.raises(ValidationError):
        PCT.validate_python(value)


@pytest.mark.parametrize("value", [1, 3, 6, 120])
def test_installments_accepts_whole_numbers_in_range(value: int) -> None:
    assert INSTALLMENTS.validate_python(value) == value


@pytest.mark.parametrize("value", [0, -1, 121, "3", 3.0, True])
def test_installments_rejects_out_of_range_or_non_integers(value: object) -> None:
    with pytest.raises(ValidationError):
        INSTALLMENTS.validate_python(value)


def test_create_proposal_in_accepts_the_documented_body() -> None:
    body = CreateProposalIn.model_validate(
        {
            "customer_message": "Can I get 40% off if I pay this week?",
            "scenario_id": "S03_exceeds_discount",
        }
    )
    assert body.scenario_id == "S03_exceeds_discount"


def test_create_proposal_in_forbids_a_policy_field() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CreateProposalIn.model_validate(
            {"customer_message": "hi", "policy": {"max_discount_pct": "100"}}
        )
    assert excinfo.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("message", ["", "x" * 501])
def test_create_proposal_in_enforces_message_length(message: str) -> None:
    with pytest.raises(ValidationError):
        CreateProposalIn.model_validate({"customer_message": message})


def test_audit_event_parses_the_blocked_example_with_optional_v11_fields_absent() -> None:
    event = AuditEvent.model_validate(
        {
            "event_id": "aud_000007",
            "seq": 7,
            "ts": "2026-11-02T15:04:31Z",
            "actor": {"type": "SYSTEM", "id": "policy_engine"},
            "action": "PROPOSAL_BLOCKED",
            "invoice_id": "INV-001",
            "proposal_id": "prop_c41d02",
            "state_from": "DRAFTED",
            "state_to": "BLOCKED",
            "severity": "CRITICAL",
            "rule": {"code": "MAX_DISCOUNT_PCT", "limit": "15", "attempted": "40", "unit": "pct"},
            "summary": "AI-proposed 40% settlement discount exceeds merchant limit of 15%",
            "paypal_called": False,
        }
    )
    assert event.source is None
    assert event.paypal_ref is None
