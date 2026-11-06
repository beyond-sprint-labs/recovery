"""Unit tests for F1-14b: text-number output validator (text_guard)."""

import contextlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.text_guard import AllowedNumbers, check_text_numbers

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "text_mismatch.json"


def _allowed(*values: str) -> AllowedNumbers:
    return AllowedNumbers(values=frozenset(Decimal(v) for v in values))


def _collect_numbers(node: object) -> set[Decimal]:
    """Collect every numeric string or integer found in a JSON-like structure."""
    found: set[Decimal] = set()
    if isinstance(node, dict):
        for child in node.values():
            found |= _collect_numbers(child)
    elif isinstance(node, list):
        for child in node:
            found |= _collect_numbers(child)
    elif isinstance(node, bool):
        pass
    elif isinstance(node, int):
        found.add(Decimal(node))
    elif isinstance(node, str):
        with contextlib.suppress(ArithmeticError):
            found.add(Decimal(node))
    return found


# ---------------------------------------------------------------------------
# PASSED cases
# ---------------------------------------------------------------------------


def test_valid_text_with_only_permitted_numbers_passes():
    allowed = _allowed("900.00", "300.00", "10", "3", "240.37", "240.36", "1021.10")

    result = check_text_numbers(["Option A: pay $900.00 today (10% settlement discount)."], allowed)

    assert result.status == "PASSED"
    assert result.unmatched == []
    assert result.numbers_in_text == ["900.00", "10"]


def test_multiple_texts_are_all_validated():
    allowed = _allowed("900.00", "300.00", "1021.10")

    result = check_text_numbers(["Pay $900.00 today.", "Total is $1021.10."], allowed)

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900.00", "1021.10"]
    assert result.unmatched == []


def test_thousands_separator_is_normalized():
    result = check_text_numbers(["Total: $1,021.10"], _allowed("1021.10"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["1021.10"]


def test_equivalent_decimal_formatting_matches_by_value():
    result = check_text_numbers(["Pay $900 today"], _allowed("900.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900"]
    assert result.unmatched == []


def test_currency_symbol_and_percentage_are_handled():
    result = check_text_numbers(["Pay $900.00 today (10% discount)."], _allowed("900.00", "10"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900.00", "10"]


def test_installment_counts_and_small_integers():
    result = check_text_numbers(["3 monthly installments of $900.00"], _allowed("3", "900.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["3", "900.00"]


def test_identifier_numbers_are_ignored():
    result = check_text_numbers(["Invoice INV-001 for $900.00"], _allowed("900.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900.00"]


def test_digit_inside_word_is_extracted_as_unsupported():
    allowed = _allowed("900.00")
    result = check_text_numbers(["item2costs $900.00"], allowed)

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["2", "900.00"]
    assert result.unmatched == ["2"]


def test_number_attached_to_word_is_extracted_as_unsupported():
    allowed = _allowed("900.00")
    result = check_text_numbers(["$900.00extra"], allowed)

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["900.00"]
    assert result.unmatched == ["900.00"]


def test_empty_and_whitespace_strings_pass():
    result = check_text_numbers(["", "   "], _allowed("900.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == []
    assert result.unmatched == []


def test_no_texts_passes():
    result = check_text_numbers([], _allowed("900.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == []
    assert result.unmatched == []


# ---------------------------------------------------------------------------
# FAILED cases
# ---------------------------------------------------------------------------


def test_altered_financial_figure_fails():
    result = check_text_numbers(["Total is $850.00"], _allowed("900.00", "300.00", "1021.10"))

    assert result.status == "FAILED"
    assert result.unmatched == ["850.00"]


def test_invented_numeric_value_fails():
    result = check_text_numbers(["The amount is $999999.99"], _allowed("900.00"))

    assert result.status == "FAILED"
    assert result.unmatched == ["999999.99"]


def test_multiple_unmatched_values_are_all_reported_in_order():
    result = check_text_numbers(["$100.00 and $200.00"], _allowed("900.00"))

    assert result.status == "FAILED"
    assert result.unmatched == ["100.00", "200.00"]


def test_extra_decimal_precision_fails():
    result = check_text_numbers(["$900.001"], _allowed("900.00"))

    assert result.status == "FAILED"
    assert result.unmatched == ["900.001"]


def test_unmatched_is_reported_across_texts():
    result = check_text_numbers(["Pay $900.00 today.", "Or $850.00 later."], _allowed("900.00"))

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["900.00", "850.00"]
    assert result.unmatched == ["850.00"]


def test_negative_amount_is_extracted_with_its_sign_even_when_zero_is_allowed():
    # Schedules contain "0.00" (n=0 interest), so zero is always an allowed value.
    # "-850.00" must never be read as a permitted "00".
    allowed = _allowed("900.00", "0.00")

    for text in ("Discount of -850.00", "Refund -850.00 today", "-$850.00"):
        result = check_text_numbers([text], allowed)

        assert result.status == "FAILED"
        assert result.numbers_in_text == ["-850.00"]
        assert result.unmatched == ["-850.00"]


def test_minus_sign_is_not_dropped_when_the_absolute_value_is_allowed():
    result = check_text_numbers(["Discount of -900.00"], _allowed("900.00"))

    assert result.status == "FAILED"
    assert result.unmatched == ["-900.00"]


def test_unicode_minus_sign_is_treated_as_a_minus():
    result = check_text_numbers(["Refund \u2212850.00 today"], _allowed("850.00"))

    assert result.status == "FAILED"
    assert result.unmatched == ["-850.00"]


def test_explicitly_allowed_negative_value_passes():
    result = check_text_numbers(["Difference of -400.00"], _allowed("-400.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["-400.00"]


def test_ranges_and_dashes_are_not_read_as_negative_numbers():
    allowed = _allowed("900.00", "300.00", "3", "6")

    for text in ("Within 3-6 days", "Pay $900.00 - $300.00 now"):
        result = check_text_numbers([text], allowed)

        assert result.status == "PASSED"
        assert result.unmatched == []

    result = check_text_numbers(["Within 3-6 days"], allowed)
    assert result.numbers_in_text == ["3", "6"]


def test_number_with_letter_suffix_is_unsupported():
    allowed = _allowed("850.00")
    result = check_text_numbers(["Pay $850.00USD today"], allowed)

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["850.00"]
    assert result.unmatched == ["850.00"]


def test_number_with_letter_prefix_is_unsupported():
    allowed = _allowed("850.00")
    result = check_text_numbers(["Payment: USD850.00"], allowed)

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["850.00"]
    assert result.unmatched == ["850.00"]


def test_scientific_notation_is_unsupported():
    allowed = _allowed("1000.00")
    result = check_text_numbers(["The payment is 1e3"], allowed)

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["1", "3"]
    assert result.unmatched == ["1", "3"]


def test_invoice_identifier_with_decimal_is_not_extracted():
    allowed = _allowed("850.00")
    result = check_text_numbers(["Invoice INV-850.00"], allowed)

    assert result.status == "PASSED"
    assert result.numbers_in_text == []
    assert result.unmatched == []


def test_letter_prefixed_negative_amount_is_unsupported():
    allowed = _allowed("850.00")

    for text in ("Refund-850.00", "USD-850.00", "Pay-$850.00"):
        result = check_text_numbers([text], allowed)

        assert result.status == "FAILED"
        assert result.numbers_in_text == ["-850.00"]
        assert result.unmatched == ["-850.00"]


def test_negative_amount_after_label_is_detected():
    allowed = _allowed("-850.00")

    for text in ("Payment: -850.00", "Payment: -$850.00"):
        result = check_text_numbers([text], allowed)

        assert result.status == "PASSED"
        assert result.numbers_in_text == ["-850.00"]
        assert result.unmatched == []


def test_invoice_identifier_requires_the_complete_inv_prefix():
    allowed = _allowed("850.00")

    for text in ("INVOICE-850.00", "MINV-850.00"):
        result = check_text_numbers([text], allowed)

        assert result.status == "FAILED"
        assert result.numbers_in_text == ["-850.00"]
        assert result.unmatched == ["-850.00"]


def test_malformed_invoice_identifier_tokens_fail_closed():
    allowed = _allowed("850.00")

    cases = {
        "Invoice INV-850.00.99": ["-850.00.99"],
        "Invoice INV-850.00extra": ["-850.00"],
        "Invoice MINV-850.00": ["-850.00"],
    }

    for text, expected in cases.items():
        result = check_text_numbers([text], allowed)

        assert result.status == "FAILED"
        assert result.numbers_in_text == expected
        assert result.unmatched == expected


def test_unicode_letter_suffix_is_not_a_valid_invoice_identifier():
    allowed = _allowed("850.00")

    for suffix in ("\u00f1", "\u00e9", "\u03a9"):
        result = check_text_numbers([f"Invoice INV-850.00{suffix}"], allowed)

        assert result.status == "FAILED"
        assert result.numbers_in_text == ["-850.00"]
        assert result.unmatched == ["-850.00"]


# ---------------------------------------------------------------------------
# Unsupported number formats fail closed (en-US only)
# ---------------------------------------------------------------------------


def test_unsupported_number_formats_fail_closed():
    allowed = _allowed("0", "1", "2", "3", "5", "900.00", "1021.50", "1.5")
    cases = {
        "Pay 900,00 today": "900,00",
        "Rate of 1,5 percent": "1,5",
        "Total 1.021,50": "1.021,50",
        "Options 1,2,3": "1,2,3",
    }

    for text, raw in cases.items():
        result = check_text_numbers([text], allowed)

        assert result.status == "FAILED"
        assert result.numbers_in_text == [raw]
        assert result.unmatched == [raw]


def test_thousands_groups_of_three_are_supported():
    result = check_text_numbers(["Balance of $1,000,000.50"], _allowed("1000000.50"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["1000000.50"]


def test_decimal_tail_of_a_rejected_identifier_is_not_extracted():
    result = check_text_numbers(["Ref INV-12.00 for $900.00"], _allowed("900.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900.00"]


# ---------------------------------------------------------------------------
# Unicode digit normalization (ASCII-only extraction, DEC-25 / F1-14b)
# ---------------------------------------------------------------------------


def test_fullwidth_digits_are_normalized_before_extraction():
    result = check_text_numbers(["Total is $\uff18\uff15\uff10.00"], _allowed("900.00"))

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["850.00"]
    assert result.unmatched == ["850.00"]


def test_fullwidth_currency_and_percent_symbols_are_normalized():
    result = check_text_numbers(
        ["\uff04\uff19\uff10\uff10.00 with \uff11\uff10\uff05 off"],
        _allowed("900.00", "10"),
    )

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900.00", "10"]


def test_non_ascii_script_digits_are_mapped_to_ascii():
    arabic_indic = "\u0668\u0665\u0660"
    devanagari = "\u096e\u096b\u0966"

    for digits in (arabic_indic, devanagari):
        result = check_text_numbers([f"Total is {digits}"], _allowed("900.00"))

        assert result.status == "FAILED"
        assert result.numbers_in_text == ["850"]
        assert result.unmatched == ["850"]


def test_permitted_figure_written_in_non_ascii_digits_passes():
    result = check_text_numbers(["Pay $\uff19\uff10\uff10.00 today"], _allowed("900.00"))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900.00"]


# ---------------------------------------------------------------------------
# AllowedNumbers
# ---------------------------------------------------------------------------


def test_allowed_numbers_accepts_a_plain_set_and_stores_a_frozenset():
    allowed = AllowedNumbers(values={Decimal("900.00")})  # type: ignore[arg-type]

    assert isinstance(allowed.values, frozenset)
    assert Decimal("900.00") in allowed.values


def test_allowed_numbers_is_immutable():
    allowed = _allowed("900.00")

    with pytest.raises(AttributeError):
        allowed.values = frozenset()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_results_are_deterministic():
    allowed = _allowed("900.00", "10", "3")
    texts = ["Pay $900.00 today (10% discount), 3 installments."]

    assert check_text_numbers(texts, allowed) == check_text_numbers(texts, allowed)


# ---------------------------------------------------------------------------
# Scenario S11: altered figure in AI-generated explanation (AC12)
# ---------------------------------------------------------------------------


def test_scenario_s11_text_number_mismatch_is_detected():
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    engine_numbers = _collect_numbers(scenario["engine_result"])
    allowed = AllowedNumbers(values=frozenset(engine_numbers))

    result = check_text_numbers([scenario["generated_explanation"]], allowed)

    expected = scenario["expected_text_number_check"]
    assert scenario["expected_rule_code"] == "TEXT_NUMBER_MISMATCH"
    assert result.status == expected["status"]
    assert result.numbers_in_text == expected["numbers_in_text"]
    assert result.unmatched == expected["unmatched"]
    assert scenario["altered_number"] in result.unmatched
