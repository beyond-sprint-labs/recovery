"""Output text-number validation for F1-14 (AC12).

Validates that every numeric value appearing in generated output text belongs to
an allowed set of figures from the finance engine, customer intent, and merchant
policy. Solely responsible for output validation; does not perform input
sanitization or prompt-injection detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.core.schemas import TextNumberCheck

# Extract numbers with optional $ prefix, thousands separators, decimal part,
# and optional % suffix. Not preceded by alphanumeric/underscore/hyphen (so
# INV-001 is ignored), not followed by alphanumeric (so hello2world is ignored).
# The negative lookahead (?!\.\d) prevents matching just the integer part of a
# decimal number that is followed by more text (e.g. $900.00extra should not
# yield 900).
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_-])\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?!\.\d)\%?(?![A-Za-z0-9])"
)


@dataclass(frozen=True)
class AllowedNumbers:
    """Set of numeric values permitted in generated output text.

    Values originate from EngineResult (including payment schedules),
    CustomerIntent parameters, merchant policy parameters, and small integers
    used for ordinals and installment counts.
    """

    values: set[Decimal]


def _normalize_number(raw: str) -> Decimal | None:
    """Normalize an extracted numeric string to Decimal.

    Strips optional thousands separators and converts to Decimal. Returns None
    if the string cannot be parsed.
    """
    cleaned = raw.replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def check_text_numbers(texts: list[str], allowed: AllowedNumbers) -> TextNumberCheck:
    """Validate that every number in the given texts belongs to the allowed set.

    Args:
        texts: List of text strings to validate (e.g. agent explanations,
            customer message drafts).
        allowed: AllowedNumbers containing the permitted Decimal values.

    Returns:
        TextNumberCheck with status PASSED if all extracted numbers are allowed,
        FAILED otherwise. ``numbers_in_text`` lists all extracted values as
        normalized strings; ``unmatched`` lists those not in the allowed set.
    """
    numbers_in_text: list[str] = []
    unmatched: list[str] = []

    for text in texts:
        for match in _NUMBER_RE.finditer(text):
            raw = match.group(1)
            value = _normalize_number(raw)
            if value is None:
                continue
            normalized = str(value)
            numbers_in_text.append(normalized)
            if value not in allowed.values:
                unmatched.append(normalized)

    status = "FAILED" if unmatched else "PASSED"
    return TextNumberCheck(
        status=status,
        numbers_in_text=numbers_in_text,
        unmatched=unmatched,
    )
