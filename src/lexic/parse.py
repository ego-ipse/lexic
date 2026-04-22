"""parse(text, grammar_path) → GrammarModel instance.

Thin entry point: compile the grammar (memoised) then parse the text.
"""

from __future__ import annotations

from pathlib import Path

from lexic.base import GrammarModel
from lexic.compile import compile_from_path


def parse(text: str, grammar_path: str | Path) -> GrammarModel:
    """Parse text against a GBNF grammar and return a typed GrammarModel instance."""
    return compile_from_path(grammar_path).parse(text)
