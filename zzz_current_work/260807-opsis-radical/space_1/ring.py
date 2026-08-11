"""The instrument's own state, as a text it can read — and saving applies it.

Opsis fits its own picture as a READING, not as furniture: the presentation
record is line-oriented text, so give it a grammar and it has spans, a spine,
a verdict and a layout like any other document. No special machinery, because
it is one more thing the standard pipeline reads.

The ring closes when saving that record APPLIES it: the parse already proved
the record well-formed, so applying is reading the lines it holds.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["GRAMMAR", "apply_record", "record"]

GRAMMAR = Path(__file__).resolve().parent / "fixtures" / "policy.gbnf"


def record(policy: dict[str, str]) -> str:
    """The policy as the record it is — one key and value per line."""
    return "".join(f"{key} {value}\n" for key, value in sorted(policy.items()))


def apply_record(text: str) -> dict[str, str]:
    """The record, poured back in. What the parse proved, this reads."""
    fresh: dict[str, str] = {}
    for line in text.splitlines():
        key, _, value = line.partition(" ")
        if key:
            fresh[key] = value
    return fresh
