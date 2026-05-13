"""META_GRAMMAR mirror parity."""

from __future__ import annotations

from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR as LEGACY
from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR as NEW


def test_meta_grammar_byte_identical():
    """META_GRAMMAR is byte-identical between the two modules."""
    assert NEW == LEGACY
