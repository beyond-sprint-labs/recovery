"""Deterministic input sanitization for untrusted customer messages (F1-14).

This module is intentionally self-contained: it uses only the Python standard
library and performs no I/O, logging, network, database, or model calls.
"""

import unicodedata
from dataclasses import dataclass

MAX_LENGTH = 500

# Unicode general categories that must be removed from customer input.
_REMOVED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})

# Control characters replaced with a space instead of being removed.
_REPLACED_CONTROL_CHARS = frozenset({"\n", "\t"})


@dataclass(frozen=True)
class SanitizedText:
    """Result of sanitizing a customer message."""

    text: str
    removed_count: int


def sanitize_customer_message(raw: str) -> SanitizedText:
    """Sanitize a potentially untrusted customer message.

    Pipeline, applied in this order:

    1. Normalize with Unicode NFKC.
    2. Remove characters in categories Cc, Cf, Cs, Co, and Cn, except ``\\n``
       and ``\\t``, which are replaced with a single space.
    3. Collapse whitespace using ``" ".join(text.split())``.
    4. Truncate to ``MAX_LENGTH`` characters.
    5. Apply a final ``strip()``.

    ``removed_count`` counts only characters removed because they belong to the
    specified Unicode categories, measured after NFKC normalization. It does
    not count newlines or tabs replaced with spaces, whitespace collapsing or
    trimming, NFKC transformations, or truncation.

    Args:
        raw: Message supplied by the customer.

    Returns:
        A ``SanitizedText`` with the sanitized text and removed count.
    """
    if not isinstance(raw, str):
        raise TypeError(
            f"sanitize_customer_message() expects raw to be str, got {type(raw).__name__}"
        )

    normalized = unicodedata.normalize("NFKC", raw)

    kept: list[str] = []
    removed_count = 0

    for char in normalized:
        category = unicodedata.category(char)

        if category in _REMOVED_CATEGORIES:
            if char in _REPLACED_CONTROL_CHARS:
                kept.append(" ")
            else:
                removed_count += 1
        else:
            kept.append(char)

    # Step 3: collapse whitespace.
    collapsed = " ".join("".join(kept).split())

    # Step 4: truncate.
    truncated = collapsed[:MAX_LENGTH]

    # Step 5: final strip.
    text = truncated.strip()

    return SanitizedText(text=text, removed_count=removed_count)
