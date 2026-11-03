"""The frozen v1.1 examples in ``contracts/examples`` must stay valid and consistent.

Frontend mocks are copies of these files, so a failure here means Frontend and Backend
would disagree about the contract.
"""

import copy
import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.schemas import (
    Alternative,
    ApproveOut,
    AuditEvent,
    AuditEventsPage,
    CustomerProposalView,
    Invoice,
    Policy,
    ProposalOut,
    ProposalStatusOut,
    RespondOut,
)
from app.core.states import assert_transition

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "examples"

ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "invoice.json": TypeAdapter(Invoice),
    "invoices.json": TypeAdapter(list[Invoice]),
    "policy.json": TypeAdapter(Policy),
    "proposal_pending.json": TypeAdapter(ProposalOut),
    "proposal_blocked.json": TypeAdapter(ProposalOut),
    "proposal_text_mismatch.json": TypeAdapter(ProposalOut),
    "approve_response.json": TypeAdapter(ApproveOut),
    "customer_proposal.json": TypeAdapter(CustomerProposalView),
    "respond_response.json": TypeAdapter(RespondOut),
    "execute_response.json": TypeAdapter(RespondOut),
    "reconcile_response.json": TypeAdapter(ProposalStatusOut),
    "audit_event_drafted.json": TypeAdapter(AuditEvent),
    "audit_event_blocked.json": TypeAdapter(AuditEvent),
    "audit_event_payment_confirmed.json": TypeAdapter(AuditEvent),
    "audit_events_page.json": TypeAdapter(AuditEventsPage),
}


def _reject_float(literal: str) -> float:
    raise AssertionError(f"float literal {literal}: money and pct must travel as strings")


def load(name: str) -> Any:
    text = (EXAMPLES_DIR / name).read_text(encoding="utf-8")
    return json.loads(text, parse_float=_reject_float)


def _find_events(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if "event_id" in node:
            yield node
        for value in node.values():
            yield from _find_events(value)
    elif isinstance(node, list):
        for item in node:
            yield from _find_events(item)


def _all_keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        keys = set(node)
        for value in node.values():
            keys |= _all_keys(value)
        return keys
    if isinstance(node, list):
        return set().union(*(_all_keys(item) for item in node)) if node else set()
    return set()


# --- every example validates -----------------------------------------------------------


def test_every_example_file_is_registered_and_none_is_missing() -> None:
    on_disk = {path.name for path in EXAMPLES_DIR.glob("*.json")}
    assert on_disk == set(ADAPTERS)
    assert len(on_disk) == 15


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_example_validates_against_its_model(name: str) -> None:
    ADAPTERS[name].validate_python(load(name))


# --- audit events across all examples ------------------------------------------------------


def test_audit_events_have_consistent_ids_and_legal_transitions() -> None:
    checked = 0
    for name in ADAPTERS:
        for event in _find_events(load(name)):
            checked += 1
            assert event["event_id"] == f"aud_{event['seq']:06d}", name
            if event["state_from"] != event["state_to"]:
                assert_transition(event["state_from"], event["state_to"])
    assert checked > 15


def test_audit_page_is_ascending_contiguous_and_next_seq_is_the_last_seq() -> None:
    page = load("audit_events_page.json")
    seqs = [item["seq"] for item in page["items"]]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
    assert page["next_seq"] == seqs[-1]


def test_payment_confirmed_event_carries_the_v11_fields() -> None:
    event = load("audit_event_payment_confirmed.json")
    assert event["action"] == "PAYMENT_CONFIRMED"
    assert event["actor"]["type"] == "PAYPAL"
    assert event["source"] == "WEBHOOK"
    assert event["paypal_ref"]
    assert event["state_from"] == "EXECUTED"
    assert event["state_to"] == "PAID"
    assert "$300.00" in event["summary"]


# --- golden figures (ROADMAP section 4.3) ----------------------------------------------------


def test_pending_proposal_uses_the_golden_figures() -> None:
    proposal = load("proposal_pending.json")
    settlement, installments = proposal["alternatives"]
    assert settlement["type"] == "settlement_discount"
    assert settlement["amount_due_now"] == "900.00"
    assert installments["type"] == "down_payment_installments"
    assert installments["amount_due_now"] == "300.00"
    assert installments["installment_amount"] == "240.37"
    assert installments["total_paid"] == "1021.10"
    assert installments["present_value"] == "1006.91"
    assert installments["schedule"][-1]["amount"] == "240.36"  # last one absorbs the residue
    assert proposal["status"] == "PENDING_MERCHANT"
    assert proposal["paypal_called"] is False


@pytest.mark.parametrize("index", [0, 1])
def test_schedule_arithmetic_is_internally_consistent(index: int) -> None:
    alternative = load("proposal_pending.json")["alternatives"][index]
    rows = alternative["schedule"]
    assert sum(Decimal(row["amount"]) for row in rows) == Decimal(alternative["total_paid"])
    assert sum(Decimal(row["interest"]) for row in rows) == Decimal(alternative["financing_cost"])
    for row in rows:
        assert Decimal(row["amount"]) == Decimal(row["principal"]) + Decimal(row["interest"])
    assert rows[0]["amount"] == alternative["amount_due_now"]
    difference = Decimal(alternative["present_value"]) - Decimal("1000.00")
    assert difference == Decimal(alternative["merchant_difference_vs_balance"])


def test_installment_principal_adds_up_to_the_invoice_balance() -> None:
    schedule = load("proposal_pending.json")["alternatives"][1]["schedule"]
    assert sum(Decimal(row["principal"]) for row in schedule) == Decimal(
        load("invoice.json")["balance"]
    )


# --- BLOCKED outputs ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("proposal_blocked.json", "MAX_DISCOUNT_PCT"),
        ("proposal_text_mismatch.json", "TEXT_NUMBER_MISMATCH"),
    ],
)
def test_blocked_examples_never_reach_paypal_and_are_critical(name: str, code: str) -> None:
    proposal = load(name)
    assert proposal["status"] == "BLOCKED"
    assert proposal["alternatives"] == []
    assert proposal["paypal_called"] is False
    assert proposal["blocked_reasons"][0]["code"] == code
    event = proposal["audit_event"]
    assert event["action"] == "PROPOSAL_BLOCKED"
    assert event["severity"] == "CRITICAL"
    assert event["paypal_called"] is False
    assert event["state_to"] == "BLOCKED"
    assert event["rule"]["code"] == code


def test_policy_block_example_matches_the_demo_numbers() -> None:
    proposal = load("proposal_blocked.json")
    assert proposal["customer_intent"]["requested_discount_pct"] == "40"
    assert proposal["attempted"][0]["computed"]["amount_due_now"] == "600.00"
    assert proposal["policy_check"]["violations"][0]["limit"] == "15"
    assert load("policy.json")["max_discount_pct"] == "15"


def test_text_mismatch_example_reports_the_unmatched_figure() -> None:
    check = load("proposal_text_mismatch.json")["text_number_check"]
    assert check["status"] == "FAILED"
    assert check["unmatched"] == ["850.00"]
    assert set(check["unmatched"]) <= set(check["numbers_in_text"])


def test_blocked_status_requires_reasons_and_vice_versa() -> None:
    blocked_without_reasons = load("proposal_blocked.json")
    blocked_without_reasons["blocked_reasons"] = []
    with pytest.raises(ValidationError):
        ProposalOut.model_validate(blocked_without_reasons)

    pending_with_reasons = load("proposal_pending.json")
    pending_with_reasons["blocked_reasons"] = [{"code": "MAX_DISCOUNT_PCT"}]
    with pytest.raises(ValidationError):
        ProposalOut.model_validate(pending_with_reasons)


# --- customer view isolation (AC4 / DEC-28) -------------------------------------------------------

CUSTOMER_TOP_LEVEL_KEYS = {
    "proposal_id",
    "invoice_id",
    "currency",
    "original_balance",
    "alternative",
    "customer_message",
    "expires_at",
    "status",
    "simulation_notice",
}
CUSTOMER_ALTERNATIVE_KEYS = {
    "type",
    "terms",
    "amount_due_now",
    "installment_amount",
    "total_paid",
    "schedule",
}
MERCHANT_ONLY_KEYS = {
    "alternatives",
    "attempted",
    "blocked_reasons",
    "policy_check",
    "text_number_check",
    "present_value",
    "merchant_difference_vs_balance",
    "financing_cost",
    "policy_ok",
    "violations",
    "audit_event",
    "audit_events",
    "paypal_called",
    "customer_intent",
    "engine_version",
    "explanation",
    "customer_message_draft",
}


def test_customer_view_has_exactly_one_alternative_and_the_documented_keys() -> None:
    view = load("customer_proposal.json")
    assert set(view) == CUSTOMER_TOP_LEVEL_KEYS
    assert isinstance(view["alternative"], dict)  # one object, never a list
    assert set(view["alternative"]) == CUSTOMER_ALTERNATIVE_KEYS


def test_customer_view_leaks_no_merchant_only_field_at_any_depth() -> None:
    assert _all_keys(load("customer_proposal.json")).isdisjoint(MERCHANT_ONLY_KEYS)


@pytest.mark.parametrize(
    "leak",
    [
        ("alternative", "present_value", "1006.91"),
        ("alternative", "merchant_difference_vs_balance", "6.91"),
        (None, "policy_check", {"status": "PASSED", "violations": []}),
        (None, "alternatives", []),
    ],
)
def test_customer_view_model_rejects_any_internal_field(leak: tuple[Any, str, Any]) -> None:
    parent, key, value = leak
    view = load("customer_proposal.json")
    (view if parent is None else view[parent])[key] = value
    with pytest.raises(ValidationError):
        CustomerProposalView.model_validate(view)


# --- cross-file consistency ----------------------------------------------------------------------


def test_the_approved_flow_is_consistent_across_files() -> None:
    pending = load("proposal_pending.json")
    approve = load("approve_response.json")
    customer = load("customer_proposal.json")
    execute = load("execute_response.json")
    invoice = load("invoice.json")

    assert (
        pending["proposal_id"]
        == approve["proposal_id"]
        == customer["proposal_id"]
        == execute["proposal_id"]
    )
    assert approve["approved_alternative"] == customer["alternative"]["type"]
    approved_type = approve["approved_alternative"]
    chosen = next(a for a in pending["alternatives"] if a["type"] == approved_type)
    for field in ("amount_due_now", "installment_amount", "total_paid", "schedule"):
        assert customer["alternative"][field] == chosen[field]
    assert customer["original_balance"] == invoice["balance"]
    assert customer["invoice_id"] == invoice["id"]
    assert execute["paypal"]["original_invoice_id"] == invoice["paypal_invoice_id"]
    assert approve["customer_link"].startswith("http")
    assert "/customer/" in approve["customer_link"]


def test_approve_response_issues_the_link_without_touching_paypal() -> None:
    approve = load("approve_response.json")
    assert approve["status"] == "PENDING_CUSTOMER"
    actions = [event["action"] for event in approve["audit_events"]]
    assert actions == ["PROPOSAL_APPROVED", "CUSTOMER_LINK_ISSUED"]
    assert not any(event["paypal_called"] for event in approve["audit_events"])


def test_execute_response_follows_the_anti_double_charge_order() -> None:
    execute = load("execute_response.json")
    assert execute["status"] == "EXECUTED"
    # AC11: the replacement is created as a draft BEFORE the original is cancelled.
    assert execute["paypal"]["steps"] == ["create_draft", "cancel_invoice", "send_invoice"]
    actions = [event["action"] for event in execute["audit_events"]]
    assert actions.index("PAYPAL_DRAFT_CREATED") < actions.index("PAYPAL_ORIGINAL_CANCELLED")
    assert actions.index("PAYPAL_ORIGINAL_CANCELLED") < actions.index("PAYPAL_INVOICE_SENT")
    assert actions[-1] == "EXECUTION_COMPLETED"


def test_decline_response_never_calls_paypal() -> None:
    declined = load("respond_response.json")
    assert declined["status"] == "DECLINED"
    assert declined["paypal"] is None
    assert not any(event["paypal_called"] for event in declined["audit_events"])


def test_reconcile_response_is_marked_as_reconciliation() -> None:
    reconciled = load("reconcile_response.json")
    assert reconciled["status"] == "EXECUTED"
    event = reconciled["audit_events"][0]
    assert event["action"] == "RECONCILED"
    assert event["source"] == "RECONCILIATION"
    assert event["state_from"] == "NEEDS_RECONCILIATION"


# --- model-level guards -------------------------------------------------------------------------


def test_alternative_terms_must_match_the_announced_type() -> None:
    alternative = copy.deepcopy(load("proposal_pending.json")["alternatives"][0])
    alternative["terms"] = {
        "down_payment_pct": "30",
        "installments": 3,
        "periodic_rate_pct": "1.5",
    }
    with pytest.raises(ValidationError):
        Alternative.model_validate(alternative)


def test_money_can_never_be_a_json_number() -> None:
    invoice = load("invoice.json")
    invoice["balance"] = 1000.0
    with pytest.raises(ValidationError):
        Invoice.model_validate(invoice)
