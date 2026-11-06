"""Stub for F1-14 (text_guard). Replaced when PR #5 is merged."""

from app.core.schemas import TextNumberCheck


def check_text_numbers(texts: list[str], allowed: list[str]) -> TextNumberCheck:
    # Always passes; real implementation will fail if AI hallucinates numbers.
    return TextNumberCheck(status="PASSED", numbers_in_text=[], unmatched=[])
