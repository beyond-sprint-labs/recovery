"""Load official agent prompts from disk."""

from functools import cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@cache
def load_prompt(filename: str) -> str:
    """Read an official, non-empty agent prompt."""
    if filename not in {
        "system_agent.txt",
        "explain_alternatives.txt",
        "customer_message.txt",
    }:
        raise ValueError("Unsupported prompt file")

    text = (PROMPT_DIR / filename).read_text(encoding="utf-8").strip()

    if not text:
        raise ValueError(f"Prompt file {filename} is empty")

    return text
