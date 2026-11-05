"""Unit tests for F1-14: text-number output validator (text_guard)."""

from decimal import Decimal

from app.services.input_sanitizer import SanitizedText, sanitize_customer_message
from app.services.text_guard import AllowedNumbers, check_text_numbers


def _allowed(*values: str) -> AllowedNumbers:
    return AllowedNumbers(values={Decimal(v) for v in values})


# ---------------------------------------------------------------------------
# PASSED cases
# ---------------------------------------------------------------------------


def test_valid_text_only_permitted_numbers_passes():
    allowed = _allowed("900.00", "300.00", "10", "3", "240.37", "240.36", "1021.10")
    result = check_text_numbers(
        ["Option A: pay $900.00 today (10% settlement discount)."],
        allowed,
    )

    assert result.status == "PASSED"
    assert result.unmatched == []
    assert "900.00" in result.numbers_in_text
    assert "10" in result.numbers_in_text


def test_valid_text_with_multiple_inputs_passes():
    allowed = _allowed("900.00", "300.00", "1021.10")
    result = check_text_numbers(
        ["Pay $900.00 today.", "Total is $1021.10."],
        allowed,
    )

    assert result.status == "PASSED"
    assert result.unmatched == []


def test_equivalent_formatting_normalizes_correctly():
    allowed = _allowed("1021.10")
    result = check_text_numbers(["Total: $1,021.10"], allowed)

    assert result.status == "PASSED"
    assert result.unmatched == []
    assert "1021.10" in result.numbers_in_text


def test_currency_symbols_and_percentages():
    allowed = _allowed("900.00", "10")
    result = check_text_numbers(["Pay $900.00 today (10% discount)."], allowed)

    assert result.status == "PASSED"
    assert result.unmatched == []


def test_installment_counts_and_small_integers():
    allowed = _allowed("3", "900.00")
    result = check_text_numbers(["3 monthly installments of $900.00"], allowed)

    assert result.status == "PASSED"
    assert result.unmatched == []


def test_identifier_numbers_are_ignored():
    allowed = _allowed("900.00")
    result = check_text_numbers(["Invoice INV-001 for $900.00"], allowed)

    assert result.status == "PASSED"
    assert result.unmatched == []
    assert "001" not in result.numbers_in_text


def test_numbers_inside_words_are_ignored():
    allowed = _allowed("900.00")
    result = check_text_numbers(["item2costs $900.00"], allowed)

    assert result.status == "PASSED"
    assert result.unmatched == []
    assert "2" not in result.numbers_in_text


def test_empty_strings_pass():
    allowed = _allowed("900.00")
    result = check_text_numbers(["", "   "], allowed)

    assert result.status == "PASSED"
    assert result.numbers_in_text == []
    assert result.unmatched == []


def test_no_texts_passes():
    allowed = _allowed("900.00")
    result = check_text_numbers([], allowed)

    assert result.status == "PASSED"
    assert result.numbers_in_text == []
    assert result.unmatched == []


# ---------------------------------------------------------------------------
# FAILED cases
# ---------------------------------------------------------------------------


def test_altered_financial_figure_fails():
    allowed = _allowed("900.00", "300.00", "1021.10")
    result = check_text_numbers(["Total is $850.00"], allowed)

    assert result.status == "FAILED"
    assert "850.00" in result.unmatched


def test_invented_numeric_value_fails():
    allowed = _allowed("900.00")
    result = check_text_numbers(["The amount is $999999.99"], allowed)

    assert result.status == "FAILED"
    assert "999999.99" in result.unmatched


def test_multiple_unmatched_values():
    allowed = _allowed("900.00")
    result = check_text_numbers(["$100.00 and $200.00"], allowed)

    assert result.status == "FAILED"
    assert "100.00" in result.unmatched
    assert "200.00" in result.unmatched


def test_decimal_precision_edge_cases():
    allowed = _allowed("900.00")
    result = check_text_numbers(["$900.001"], allowed)

    assert result.status == "FAILED"
    assert "900.001" in result.unmatched


def test_number_attached_to_word_is_not_extracted():
    allowed = _allowed("900.00")
    result = check_text_numbers(["$900.00extra"], allowed)

    assert result.status == "PASSED"
    assert result.numbers_in_text == []
    assert result.unmatched == []


# ---------------------------------------------------------------------------
# Integration with sanitizer
# ---------------------------------------------------------------------------


def test_sanitized_text_then_validate_numbers():
    """Verify text_guard works with sanitized input pipeline."""
    raw = "Option A: pay $900.00 today (10% settlement discount)."
    sanitized = sanitize_customer_message(raw)
    assert isinstance(sanitized, SanitizedText)

    allowed = _allowed("900.00", "10")
    result = check_text_numbers([sanitized.text], allowed)

    assert result.status == "PASSED"
    assert result.unmatched == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_results():
    allowed = _allowed("900.00", "10", "3")
    texts = ["Pay $900.00 today (10% discount), 3 installments."]

    first = check_text_numbers(texts, allowed)
    second = check_text_numbers(texts, allowed)

    assert first == second
    assert first.status == second.status
    assert first.numbers_in_text == second.numbers_in_text
    assert first.unmatched == second.unmatched
