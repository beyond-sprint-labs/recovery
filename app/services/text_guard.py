"""Output text-number validation for F1-14b (AC12).

Validates that every numeric value appearing in generated output text belongs to
an allowed set of figures coming from the finance engine, the customer intent and
the merchant policy.

Scope (DEC-25): this module validates OUTPUT only. Input hygiene lives in
``input_sanitizer`` and semantic prompt-injection detection is out of scope
(F2-01). It uses only the Python standard library and performs no I/O, logging,
network, database, or model calls.

Supported number format (en-US, ASCII digits after normalization):

    [-] [$] digits [. digits] [%]

where ``digits`` may use "," as a thousands separator in groups of exactly three
(``1,021.10``). A leading minus is part of the figure, so ``-850.00`` is the
value -850.00. Any other grouping or decimal convention, such as ``900,00``,
``1,5``, ``1.021,50`` or ``1,2,3``, is UNSUPPORTED and fails closed: it is
reported verbatim in both ``numbers_in_text`` and ``unmatched``, so the proposal
is blocked instead of being misread.

Numbers adjacent to letters (before or after) are also unsupported: they are
extracted and reported in ``numbers_in_text`` and ``unmatched`` so that
``Pay $850.00USD today`` and ``USD850.00`` fail closed instead of being silently
ignored.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from app.core.schemas import TextNumberCheck

__all__ = ["AllowedNumbers", "check_text_numbers"]

# Candidate numeric token: digits optionally joined by "." or ",". Digits are
# strictly ASCII [0-9]; text is normalized by ``_normalize_text`` before matching.
#
# - Not preceded by a digit (so part of a larger number is not matched again).
# - Not preceded by a digit plus "." or "," (so when the head of a number is
#   rejected, its tail, for example the "00" of "INV-12.00", is not extracted).
# - Not followed by a separator plus a digit (so a token is never cut in the middle).
#
# Numbers preceded by a letter/underscore (as in "USD850.00" or "INV-001") or
# followed by a letter (as in "$850.00USD") are still extracted but flagged as
# unsupported below, so they fail closed instead of being silently ignored.
# A hyphen sign preceded by a letter (as in "INV-001") is part of an identifier
# and is skipped entirely.
_NUMBER_RE = re.compile(
    r"(?<![0-9])"
    r"(?<![0-9][.,])"
    r"(?P<neg>-)?"
    r"\$?"
    r"(?P<token>[0-9]+(?:[.,][0-9]+)*)"
    r"%?"
    r"(?![.,][0-9])"
)

# A token is supported only if it follows the en-US grammar described above.
_SUPPORTED_TOKEN_RE = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?")

_UNICODE_MINUS = "\u2212"


@dataclass(frozen=True)
class AllowedNumbers:
    """Set of numeric values permitted in generated output text.

    Values originate from ``EngineResult`` (including payment schedules),
    ``CustomerIntent`` parameters, merchant policy parameters, and small integers
    used for ordinals and installment counts. Any iterable of ``Decimal`` is
    accepted and stored as an immutable ``frozenset``. Membership is by numeric
    value, so ``Decimal("850")`` and ``Decimal("850.00")`` are equivalent, and a
    negative figure only matches an explicitly allowed negative value.
    """

    values: frozenset[Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", frozenset(self.values))


def _normalize_text(text: str) -> str:
    """Prepare text for ASCII-only number extraction.

    Applies NFKC, maps the Unicode minus sign (U+2212) to ``-``, and maps every
    Unicode decimal digit (``Nd``) to ASCII. NFKC folds full-width forms such as
    ``\uff18\uff15\uff10``, ``\uff04`` and ``\uff05``; digits from other scripts
    (for example Arabic-Indic ``\u0668\u0665\u0660``) and U+2212 survive NFKC, so
    they are mapped explicitly.
    Without this step an output could carry an altered figure that the ASCII-only
    extraction would miss.
    """
    normalized = unicodedata.normalize("NFKC", text).replace(_UNICODE_MINUS, "-")
    return "".join(
        str(unicodedata.decimal(char)) if unicodedata.category(char) == "Nd" else char
        for char in normalized
    )


def check_text_numbers(texts: list[str], allowed: AllowedNumbers) -> TextNumberCheck:
    """Validate that every number in the given texts belongs to the allowed set.

    Args:
        texts: Text strings to validate (for example agent explanations or
            customer message drafts).
        allowed: The permitted numeric values.

    Returns:
        ``TextNumberCheck`` with status ``PASSED`` when every extracted number is
        allowed and ``FAILED`` otherwise. ``numbers_in_text`` lists all extracted
        values as normalized strings, in order of appearance; ``unmatched`` lists
        those that are not in the allowed set, plus any number written in an
        unsupported format (see the module docstring).
    """
    numbers_in_text: list[str] = []
    unmatched: list[str] = []

    for text in texts:
        normalized_text = _normalize_text(text)
        for match in _NUMBER_RE.finditer(normalized_text):
            sign = match.group("neg") or ""
            token = match.group("token")
            start, end = match.span()

            # A hyphen sign preceded by a letter/underscore is part of an
            # identifier (e.g. "INV-001"), not a negative number. Skip it
            # entirely so identifiers are not mistaken for amounts.
            if sign and start > 0 and normalized_text[start - 1].isalpha():
                continue

            # A number preceded by a letter/underscore (as in "USD850.00" or
            # "INV-001") or followed by a letter (as in "$850.00USD") is an
            # unsupported alphanumeric token and must fail closed.
            preceded_by_letter = start > 0 and normalized_text[start - 1].isalpha()
            followed_by_letter = end < len(normalized_text) and normalized_text[end].isalpha()
            adjacent_to_letter = preceded_by_letter or followed_by_letter

            if _SUPPORTED_TOKEN_RE.fullmatch(token) is None or adjacent_to_letter:
                numbers_in_text.append(f"{sign}{token}")
                unmatched.append(f"{sign}{token}")
                continue

            value = Decimal(f"{sign}{token.replace(',', '')}")
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
