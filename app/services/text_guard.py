"""Output text-number validation for F1-14 (AC12).

Validates that every numeric value appearing in generated output text belongs to
an allowed set of figures from the finance engine, customer intent, and merchant
policy. Solely responsible for output validation; does not perform input
sanitization or prompt-injection detection.

Supported numeric formats:
- Plain integers: ``3``, ``10``
- Plain decimals: ``900.00``, ``0.50``, ``1021.10``
- Currency amounts: ``$900.00``, ``$1,021.10``
- Negative amounts: ``-850.00``, ``-0.50``, ``-$850.00``
- Percentages: ``10%``
- Thousands separators: ``1,021.10`` (comma groups exactly three digits)

Not supported and never silently extracted:
- European-style comma decimals: ``900,00`` is not matched at all.
- Numbers embedded in identifiers: ``INV-001`` is ignored.
- Numbers embedded in words: ``hello2world`` is ignored.
- Numbers attached to trailing text: ``$900.00extra`` is ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.core.schemas import TextNumberCheck

# Extract numbers with optional leading minus sign, optional $ prefix,
# thousands separators (comma groups exactly three digits), optional decimal
# part, and optional % suffix.
#
# Lookbehind (?<![A-Za-z0-9_-,]) prevents matching numbers that are part of
# identifiers such as INV-001 (the hyphen before 001 blocks the match) and
# prevents extracting fragments of European-style comma decimals such as
# 900,00 (the comma before 00 blocks the fragment match).
#
# Lookahead (?!\.\d) prevents matching just the integer part of a decimal
# followed by more text (e.g. $900.00extra should not yield 900).
#
# Lookahead (?!,\d{1,2}(?!\d)) prevents silently extracting the integer part
# of a European-style comma decimal such as 900,00 (the comma followed by one
# or two digits is not a valid thousands separator in this parser).
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_,-])(-?\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\$?\d+(?:\.\d+)?)(?!\.\d)(?!,\d{1,2}(?!\d))\%?(?![A-Za-z0-9])"
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

    Strips optional currency symbols and thousands separators and converts to
    Decimal. Returns None if the string cannot be parsed.
    """
    cleaned = raw.replace(",", "").replace("$", "")
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
