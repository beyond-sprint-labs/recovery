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
value -850.00. Any other grouping or decimal convention (``900,00``, ``1,5``,
``1.021,50``, ``1,2,3``) is UNSUPPORTED and fails closed: it is reported verbatim
in both ``numbers_in_text`` and ``unmatched``.

Boundary allow-list (default deny): a figure is only accepted when the character
before it and the character after it are the start/end of the text, whitespace,
or one of a small set of ASCII punctuation marks (see ``_LEFT_SAFE`` and
``_RIGHT_SAFE``). Anything else touching a figure (letters, other currency
symbols, apostrophes, dots, zero-width or bidi characters, en dashes, ...) makes
it unsupported. This is deliberate: a deny-list of "dangerous" neighbours is
always one character short. A bare figure separated from a previous digit by
whitespace (``1 021.10``) is also unsupported, because it can be read as one
number but extracted as two.

Invoice identifiers: only the identifiers listed in ``AllowedNumbers.invoice_ids``
(for example ``INV-001``) are ignored. Any other ``INV-...`` text, including
``INV-850`` or ``INV-850.00``, is validated like any other number.

Known limits (documented, not silently accepted):
- Membership check only: it proves a figure exists in the engine output, not that
  the sentence attaches it to the right concept.
- Figures written in words ("nine hundred") are not detected.
- Dates and ordinals ("2026-12-11", "1st") fail closed unless their digits are
  allowed; prompts must avoid them.
- Two figures separated only by whitespace ("300.00 240.37") fail closed.
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
# - Not preceded by a digit, nor by a digit plus "." or "," (so the tail of a
#   rejected number is not extracted again).
# - Not followed by a separator plus a digit (a token is never cut in the middle).
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
_ASCII_DIGITS = frozenset("0123456789")
_WHITESPACE = frozenset(" \t\n\r")
# Characters allowed immediately before / after a figure (besides whitespace).
# U+2014 (em dash) and the curly double quotes are common in prose; the en dash
# and every apostrophe are intentionally excluded (minus sign / digit separator).
_LEFT_SAFE = frozenset('([{"\u201c-:;,\u2014')
_RIGHT_SAFE = frozenset(')]}"\u201d-:;,.!?\u2014')


@dataclass(frozen=True)
class AllowedNumbers:
    """Set of numeric values permitted in generated output text.

    Values originate from ``EngineResult`` (including payment schedules),
    ``CustomerIntent`` parameters, merchant policy parameters, and small integers
    used for ordinals and installment counts. Membership is by numeric value, so
    ``Decimal("850")`` and ``Decimal("850.00")`` are equivalent, and a negative
    figure only matches an explicitly allowed negative value.

    ``invoice_ids`` lists the invoice identifiers (for example ``INV-001``) that
    may appear verbatim in the text; their digits are not treated as figures.
    """

    values: frozenset[Decimal]
    invoice_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", frozenset(self.values))
        invoice_ids = frozenset(self.invoice_ids)
        if any(not identifier.strip() for identifier in invoice_ids):
            raise ValueError("invoice_ids must not contain blank identifiers")
        object.__setattr__(self, "invoice_ids", invoice_ids)


def _normalize_text(text: str) -> str:
    """Prepare text for ASCII-only number extraction.

    Applies NFKC, maps the Unicode minus sign (U+2212) to ``-``, and maps every
    Unicode decimal digit (``Nd``) to ASCII. NFKC folds full-width forms and the
    various no-break spaces; digits from other scripts and U+2212 survive NFKC,
    so they are mapped explicitly. Without this step an output could carry an
    altered figure that the ASCII-only extraction would miss.
    """
    normalized = unicodedata.normalize("NFKC", text).replace(_UNICODE_MINUS, "-")
    return "".join(
        str(unicodedata.decimal(char)) if unicodedata.category(char) == "Nd" else char
        for char in normalized
    )


def _invoice_id_pattern(invoice_ids: frozenset[str]) -> re.Pattern[str] | None:
    """Match only the listed identifiers, not glued to word characters or decimals."""
    if not invoice_ids:
        return None
    ordered = sorted((_normalize_text(i) for i in invoice_ids), key=len, reverse=True)
    alternatives = "|".join(re.escape(identifier) for identifier in ordered)
    return re.compile(
        rf"(?<![A-Za-z0-9_])(?:{alternatives})(?![A-Za-z0-9_%]|[.,][0-9])",
        re.IGNORECASE | re.ASCII,
    )


def _is_unsupported(text: str, token: str, start: int, end: int) -> bool:
    """Return True when a candidate figure must fail closed."""
    if _SUPPORTED_TOKEN_RE.fullmatch(token) is None:
        return True

    prev = text[start - 1] if start > 0 else None
    nxt = text[end] if end < len(text) else None
    if prev is not None and prev not in _WHITESPACE and prev not in _LEFT_SAFE:
        return True
    if nxt is not None and nxt not in _WHITESPACE and nxt not in _RIGHT_SAFE:
        return True

    # "1 021.10": a bare figure split from a previous digit by whitespace.
    if text[start] in _ASCII_DIGITS and prev in _WHITESPACE:
        before = text[:start].rstrip(" \t\n\r")
        if before and before[-1] in _ASCII_DIGITS:
            return True
    return False


def check_text_numbers(texts: list[str], allowed: AllowedNumbers) -> TextNumberCheck:
    """Validate that every number in the given texts belongs to the allowed set.

    Args:
        texts: Text strings to validate (for example agent explanations or
            customer message drafts). Validate exactly the strings that will be
            persisted or sent.
        allowed: The permitted numeric values and invoice identifiers.

    Returns:
        ``TextNumberCheck`` with status ``PASSED`` when every extracted number is
        allowed and ``FAILED`` otherwise. ``numbers_in_text`` lists all extracted
        values as normalized strings, in order of appearance; ``unmatched`` lists
        those that are not allowed, plus any figure in an unsupported format or
        with unsafe neighbours (see the module docstring).
    """
    invoice_ids_re = _invoice_id_pattern(allowed.invoice_ids)
    numbers_in_text: list[str] = []
    unmatched: list[str] = []

    for text in texts:
        normalized_text = _normalize_text(text)
        if invoice_ids_re is not None:
            # A space keeps neighbouring tokens separated after the removal.
            normalized_text = invoice_ids_re.sub(" ", normalized_text)

        for match in _NUMBER_RE.finditer(normalized_text):
            sign = match.group("neg") or ""
            token = match.group("token")
            start, end = match.span()
            raw = f"{sign}{token}"

            if _is_unsupported(normalized_text, token, start, end):
                numbers_in_text.append(raw)
                unmatched.append(raw)
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
