"""Unit tests for F1-14: input sanitizer."""

import random
import unicodedata

import pytest

from app.services.input_sanitizer import (
    MAX_LENGTH,
    SanitizedText,
    sanitize_customer_message,
)

LIMIT = 500


def test_public_limit_is_500():
    assert MAX_LENGTH == 500


def test_sanitized_text_is_frozen_dataclass():
    from dataclasses import is_dataclass

    assert is_dataclass(SanitizedText)
    assert SanitizedText.__dataclass_params__.frozen is True


def test_sanitized_text_has_expected_fields():
    fields = {f.name for f in SanitizedText.__dataclass_fields__.values()}
    assert fields == {"text", "removed_count"}


def test_function_returns_sanitized_text():
    result = sanitize_customer_message("hello")
    assert isinstance(result, SanitizedText)
    assert result.text == "hello"
    assert result.removed_count == 0


# ---------------------------------------------------------------------------
# Required cases
# ---------------------------------------------------------------------------


def test_zero_width_space_is_removed():
    result = sanitize_customer_message("4\u200b0%")

    assert result.text == "40%"
    assert result.removed_count == 1


def test_rlo_is_removed():
    result = sanitize_customer_message("\u202eHello\u202c")

    assert result.text == "Hello"
    assert result.removed_count == 2


def test_null_character_is_removed():
    result = sanitize_customer_message("Hello\x00World")

    assert result.text == "HelloWorld"
    assert result.removed_count == 1
    assert "\x00" not in result.text


def test_whitespace_only_input_produces_empty_string():
    result = sanitize_customer_message("   \n\t  ")

    assert result.text == ""
    assert result.removed_count == 0


def test_exactly_500_characters_is_preserved():
    raw = "a" * LIMIT

    result = sanitize_customer_message(raw)

    assert result.text == "a" * LIMIT
    assert len(result.text) == LIMIT
    assert result.removed_count == 0


def test_501_characters_truncated_to_500_without_count_increase():
    raw = "a" * (LIMIT + 1)

    result = sanitize_customer_message(raw)

    assert result.text == "a" * LIMIT
    assert len(result.text) == LIMIT
    assert result.removed_count == 0


def test_normal_english_text_preserved():
    raw = "Can I pay $900 today?"

    result = sanitize_customer_message(raw)

    assert result.text == raw
    assert result.removed_count == 0


def test_normal_spanish_text_preserved():
    raw = "¿Es posible pagar hoy?"

    result = sanitize_customer_message(raw)

    assert result.text == raw
    assert result.removed_count == 0


def test_newline_and_tab_become_spaces():
    result = sanitize_customer_message("Hello\n\tWorld")

    assert result.text == "Hello World"
    assert result.removed_count == 0


def test_u2028_and_u2029_are_collapsed_as_whitespace():
    result = sanitize_customer_message("Hello\u2028World\u2029!")

    assert result.text == "Hello World !"
    assert result.removed_count == 0


def test_nfkc_fullwidth_digits_and_symbols():
    result = sanitize_customer_message("\uff04\uff19\uff10\uff10")

    assert result.text == "$900"
    assert result.removed_count == 0


def test_unassigned_code_point_u0378_is_removed():
    result = sanitize_customer_message("left\u0378right")

    assert result.text == "leftright"
    assert result.removed_count == 1


def test_empty_string():
    result = sanitize_customer_message("")

    assert result.text == ""
    assert result.removed_count == 0


def test_unusual_unicode_strings():
    raw = "\u0000\u200b\u202e\uff1a\u0378\U0010ffff"

    result = sanitize_customer_message(raw)

    assert result.text == ":"
    assert result.removed_count == 5


def test_sanitization_is_deterministic():
    raw = "  \u200bHello\x00World\u202e  "

    first = sanitize_customer_message(raw)
    second = sanitize_customer_message(raw)

    assert first == second
    assert first.text == second.text
    assert first.removed_count == second.removed_count


def test_non_string_input_raises_type_error():
    with pytest.raises(TypeError):
        sanitize_customer_message(None)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        sanitize_customer_message(42)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        sanitize_customer_message(b"hello")  # type: ignore[arg-type]


def test_no_exception_for_valid_string_input():
    for raw in ["", "hello", "\x00", "\uffff", "\U0010ffff", " " * 1000]:
        result = sanitize_customer_message(raw)
        assert isinstance(result, SanitizedText)
        assert isinstance(result.text, str)
        assert isinstance(result.removed_count, int)
        assert result.removed_count >= 0
        assert len(result.text) <= LIMIT


# ---------------------------------------------------------------------------
# Additional boundary and regression cases
# ---------------------------------------------------------------------------


def test_format_characters_are_removed():
    for char in ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u061c"]:
        result = sanitize_customer_message(f"a{char}b")

        assert result.text == "ab"
        assert result.removed_count == 1


def test_each_format_character_is_counted():
    result = sanitize_customer_message("\u200b\u202e\ufeff")

    assert result.text == ""
    assert result.removed_count == 3


def test_private_use_characters_are_removed():
    result = sanitize_customer_message(f"a{chr(0xE000)}b")

    assert result.text == "ab"
    assert result.removed_count == 1


def test_surrogate_characters_are_removed():
    result = sanitize_customer_message(f"a{chr(0xD800)}b")

    assert result.text == "ab"
    assert result.removed_count == 1


def test_control_characters_other_than_newline_tab_are_removed():
    for control in ["\x00", "\x01", "\x1f", "\x7f", "\x85"]:
        result = sanitize_customer_message(f"left{control}right")

        assert result.text == "leftright"
        assert result.removed_count == 1


def test_nbsp_is_collapsed_as_whitespace_without_removal():
    result = sanitize_customer_message("left\u00a0right")

    assert result.text == "left right"
    assert result.removed_count == 0


def test_repeated_spaces_are_collapsed_without_count_increase():
    result = sanitize_customer_message("Hello    world")

    assert result.text == "Hello world"
    assert result.removed_count == 0


def test_leading_and_trailing_whitespace_trimmed_without_count_increase():
    result = sanitize_customer_message("  hello  ")

    assert result.text == "hello"
    assert result.removed_count == 0


def test_truncation_does_not_increase_removed_count():
    raw = "a" * 2000

    result = sanitize_customer_message(raw)

    assert len(result.text) == LIMIT
    assert result.removed_count == 0


def test_nfkc_ligature_is_normalized_without_removal():
    result = sanitize_customer_message("\ufb01")

    assert result.text == "fi"
    assert result.removed_count == 0


def test_nfkc_circled_digit_is_normalized_without_removal():
    result = sanitize_customer_message("\u2460")

    assert result.text == "1"
    assert result.removed_count == 0


def test_output_never_exceeds_limit():
    raw = "a" * 10000

    result = sanitize_customer_message(raw)

    assert len(result.text) <= LIMIT


def test_spanish_accents_and_punctuation_are_preserved():
    raw = "Sí, señor. ¿Es posible?"

    result = sanitize_customer_message(raw)

    assert result.text == raw
    assert result.removed_count == 0


def test_emoji_is_preserved():
    raw = "Hola 😊"

    result = sanitize_customer_message(raw)

    assert result.text == raw
    assert result.removed_count == 0


# ---------------------------------------------------------------------------
# Fuzz/regression: 5000 randomized cases with fixed seed
# ---------------------------------------------------------------------------


def test_randomized_cases_deterministic_and_safe():
    random.seed(1414)

    alphabet = [
        *list("abcXYZ 0123456789$%?.,\n\t"),
        "\u200b",
        "\u202e",
        "\u202c",
        "\u2066",
        "\u2069",
        "\x00",
        "\x01",
        "\x7f",
        "\u00a0",
        "\u1680",
        "\u2028",
        "\ue000",
        chr(0xD800),
        chr(0x10FFFF),
        "\ufb01",
        "\u2460",
        "\uff04",
        "\uff19",
        "\u0301",
        "é",
        "ñ",
        "¿",
        "¡",
        "😊",
        "\u0378",
        "\u2029",
    ]
    removed_categories = {"Cc", "Cf", "Cs", "Co", "Cn"}
    replaced_control_chars = {"\n", "\t"}

    for _ in range(5000):
        raw = "".join(random.choice(alphabet) for _ in range(random.randrange(0, 700)))

        result = sanitize_customer_message(raw)

        assert isinstance(result, SanitizedText)
        assert isinstance(result.text, str)
        assert isinstance(result.removed_count, int)
        assert len(result.text) <= LIMIT
        assert result.text == result.text.strip()
        assert "  " not in result.text
        assert result.removed_count >= 0

        # Deterministic.
        assert sanitize_customer_message(raw) == result

        # Removed count only counts removed category characters after NFKC.
        normalized = unicodedata.normalize("NFKC", raw)
        removed_by_category = sum(
            1
            for ch in normalized
            if unicodedata.category(ch) in removed_categories and ch not in replaced_control_chars
        )
        assert result.removed_count == removed_by_category
