"""META_GRAMMAR mirror parity."""

from __future__ import annotations

from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR


def test_meta_grammar_is_non_empty_string():
    """META_GRAMMAR is a non-empty string."""
    assert isinstance(META_GRAMMAR, str)
    assert len(META_GRAMMAR) > 0
