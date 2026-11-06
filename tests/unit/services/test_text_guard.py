"""Unit tests for F1-14b: text-number output validator (text_guard)."""

import contextlib
import json
import unicodedata
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.text_guard import AllowedNumbers, check_text_numbers

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "text_mismatch.json"
INVOICE_IDS = ("INV-001", "INV-0042")


def _allowed(*values: str, invoice_ids: tuple[str, ...] = ()) -> AllowedNumbers:
    return AllowedNumbers(
        values=frozenset(Decimal(v) for v in values),
        invoice_ids=frozenset(invoice_ids),
    )


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
    allowed = _allowed("900.00", invoice_ids=("INV-001",))

    result = check_text_numbers(["Invoice INV-001 for $900.00"], allowed)

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


def test_invoice_identifier_with_decimal_tail_fails_closed():
    allowed = _allowed("850.00", "0.00", invoice_ids=("INV-001",))

    result = check_text_numbers(["Invoice INV-850.00"], allowed)

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["-850.00"]
    assert result.unmatched == ["-850.00"]


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


def test_decimal_tail_of_a_non_identifier_is_not_hidden():
    allowed = _allowed("900.00", invoice_ids=("INV-001",))

    result = check_text_numbers(["Ref INV-12.00 for $900.00"], allowed)

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["-12.00", "900.00"]
    assert result.unmatched == ["-12.00"]


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


def test_blank_invoice_identifier_is_rejected():
    with pytest.raises(ValueError, match="blank"):
        AllowedNumbers(values=frozenset(), invoice_ids=frozenset({"  "}))


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_results_are_deterministic():
    allowed = _allowed("900.00", "10", "3")
    texts = ["Pay $900.00 today (10% discount), 3 installments."]

    assert check_text_numbers(texts, allowed) == check_text_numbers(texts, allowed)


# ---------------------------------------------------------------------------
# Adversarial boundaries: default deny
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["Refund-850.00", "USD-850.00", "Pay-$850.00", "Pay-850.00 today"],
)
def test_negative_amount_glued_to_a_word_fails_closed(text):
    # Fails closed even when 850.00 and -850.00 are both explicitly allowed.
    result = check_text_numbers([text], _allowed("0.00", "850.00", "-850.00"))

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["-850.00"]
    assert result.unmatched == ["-850.00"]


@pytest.mark.parametrize(
    "text",
    [
        "Invoice INV-$850.00",
        "Invoice INV-850%",
        "Invoice INV-850",
        "Invoice INV-001extra",
        "Invoice INV-001.50",
    ],
)
def test_identifier_lookalikes_do_not_hide_figures(text):
    allowed = _allowed("0.00", "1", "850", "850.00", invoice_ids=INVOICE_IDS)

    result = check_text_numbers([text], allowed)

    assert result.status == "FAILED"
    assert result.unmatched


@pytest.mark.parametrize(
    "text",
    [
        "Invoice INV-001 for $900.00",
        "Invoice inv-001, total $900.00.",
        "(INV-0042) is $900.00",
    ],
)
def test_declared_invoice_identifiers_are_ignored_in_any_context(text):
    result = check_text_numbers([text], _allowed("900.00", invoice_ids=INVOICE_IDS))

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["900.00"]


@pytest.mark.parametrize(
    "text",
    [
        "Invoice INV-850",
        "Invoice INV-850.00",
        "Invoice INV-850%",
    ],
)
def test_identifier_shaped_figures_are_not_hidden(text):
    result = check_text_numbers([text], _allowed("0.00", invoice_ids=("INV-001",)))

    assert result.status == "FAILED"


@pytest.mark.parametrize(
    "text",
    [
        "Pay $3 240.37 now",
        "Pay $3'240.37 now",
        "Pay $3\u200b240.37 now",
        "Refund \u2013240.37",
    ],
)
def test_demo_figures_cannot_be_recombined_across_separators(text):
    allowed = _allowed("0.00", "3", "240.37", "240.36", "1021.10", "300.00")

    assert check_text_numbers([text], allowed).status == "FAILED"


@pytest.mark.parametrize(
    "text",
    [
        "Pay $1 021.10 today",  # space as thousands separator
        "Pay 1 021.10 today",
        "Pay $1\u00a0021.10 today",  # no-break space, folded to a space by NFKC
        "Pay $1'021.10 today",  # Swiss apostrophe
        "Pay $1\u2019021.10 today",  # typographic apostrophe
        "Pay $1\u00b7021.10 today",  # middle dot
        "Pay $10\u066b00 today",  # Arabic decimal separator
        "Pay $85\u200b0.00 today",  # zero-width space inside the figure
        "Pay $85\u202e0.00 today",  # bidi override inside the figure
    ],
)
def test_digit_group_separators_fail_closed(text):
    allowed = _allowed("0.00", "1", "10", "21.10", "85", "1021.10", "850.00")

    assert check_text_numbers([text], allowed).status == "FAILED"


@pytest.mark.parametrize(
    "text",
    [
        "Pay \u20ac850.00 today",
        "Pay 850.00\u20ac today",
        "Pay \u00a3850.00 today",
        "Pay 850.00\u00a5 today",
        "Pay Rs.850.00 today",
        "Pay .850 today",
        "Pay 0x354 today",
        "Pay 1_000 today",
        "Pay \u00bd now",
    ],
)
def test_foreign_symbols_and_odd_notations_fail_closed(text):
    allowed = _allowed("0", "1", "2", "354", "850", "850.00", "1000")

    assert check_text_numbers([text], allowed).status == "FAILED"


@pytest.mark.parametrize("dash", ["\u2013", "\u2010", "\u2011", "\ufe63", "\uff0d"])
def test_dash_variants_never_turn_a_negative_into_a_pass(dash):
    result = check_text_numbers([f"Refund {dash}850.00 today"], _allowed("850.00", "0.00"))

    assert result.status == "FAILED"


def test_em_dash_and_curly_double_quotes_between_words_are_accepted():
    allowed = _allowed("300.00", "900.00")

    result = check_text_numbers(["Total\u2014$300.00 or \u201c$900.00\u201d"], allowed)

    assert result.status == "PASSED"
    assert result.numbers_in_text == ["300.00", "900.00"]


# Characters that legitimately fold to a safe neighbour are excluded from the sweep:
# ASCII punctuation allowed around figures, whitespace, and U+2212, which the module
# maps to "-" on purpose.
_SWEEP_SKIP = frozenset('$%-()[]{}":;,.!? \t\n\r\u2014\u2212')


def _boundary_chars() -> Iterator[str]:
    """Every BMP letter, mark, symbol or format char that cannot fold to a safe char."""
    for codepoint in range(0x10000):
        char = chr(codepoint)
        category = unicodedata.category(char)
        if category[0] not in {"L", "M", "S"} and category != "Cf":
            continue
        folded = unicodedata.normalize("NFKC", char)
        if any(c in _SWEEP_SKIP or c.isspace() or unicodedata.category(c) == "Nd" for c in folded):
            continue
        yield char


def test_no_letter_mark_symbol_or_format_char_can_touch_a_figure():
    allowed = _allowed("850.00", "850", "0.00")
    leaks = [
        f"U+{ord(char):04X}"
        for char in _boundary_chars()
        for text in (f"Pay{char}850.00 today", f"Pay 850.00{char} today")
        if check_text_numbers([text], allowed).status == "PASSED"
    ]

    assert leaks == []


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


# ---------------------------------------------------------------------------
# Joined figures and plain integer ranges (Oscar's regression: Pay 900.00-850.00)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Pay 900.00-850.00",
        "Pay $900.00-$850.00",
        "Pay $900.00-850.00",
        "Pay 900.00-$850.00",
        "Pay 10%-20% off",
        "Pay 1,000-850 now",
        "Pay 900.00\u2014850.00",
        "Pay 900.00:850.00",
        "Pay $900.00;$850.00",
        "Pay $900.00,$850.00",
    ],
)
def test_figures_joined_by_punctuation_fail_closed(text):
    # Both figures are allowed: the failure must come from the ambiguous join itself.
    allowed = _allowed("0.00", "10", "20", "850", "850.00", "900.00", "1000")

    assert check_text_numbers([text], allowed).status == "FAILED"


def test_hyphenated_decimal_figures_report_both_amounts():
    result = check_text_numbers(["Pay 900.00-850.00"], _allowed("900.00", "850.00"))

    assert result.status == "FAILED"
    assert result.numbers_in_text == ["900.00", "850.00"]
    assert result.unmatched == ["900.00", "850.00"]


@pytest.mark.parametrize(
    "text",
    [
        "Within 3-6 days",
        "Within (3-6) days",
        "Within 3-6, days",
        "Between 10-12 days",
    ],
)
def test_plain_integer_ranges_are_still_supported(text):
    result = check_text_numbers([text], _allowed("3", "6", "10", "12"))

    assert result.status == "PASSED"
    assert result.unmatched == []
