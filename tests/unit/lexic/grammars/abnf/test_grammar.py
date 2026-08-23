"""Tests for lexic.grammars.abnf.grammar — the native ABNF self-grammar.

The grammar's shape (rule count, canonical form, start rule, the self-hosting
round-trip) is pinned in ``tests/unit/lexic/grammars/test_abnf.py``; this
file targets the module's own ``_mark`` helper and the case-insensitive
marker-letter classes it builds.
"""

from __future__ import annotations

from lexic.grammars.abnf.grammar import (
    ABNF_GRAMMAR,
    MARK_B,
    MARK_D,
    MARK_I,
    MARK_S,
    MARK_X,
    _mark,
)
from lexic.ir import IrAst, IrCharClass, IrChr


def test_mark_builds_a_case_insensitive_two_point_char_class():
    """``_mark`` returns a two-point class covering upper and lower case."""
    marker = _mark("x")
    assert marker == IrCharClass(IrChr("X"), IrChr("x"))


def test_the_module_level_markers_cover_the_five_prefix_letters():
    """Each module-level MARK_* constant matches its own ``_mark`` call."""
    assert MARK_X == _mark("x")
    assert MARK_D == _mark("d")
    assert MARK_B == _mark("b")
    assert MARK_S == _mark("s")
    assert MARK_I == _mark("i")


def test_abnf_grammar_is_an_irast_starting_at_rulelist():
    """The assembled self-grammar is an IrAst rooted at ``rulelist``."""
    assert isinstance(ABNF_GRAMMAR, IrAst)
    assert ABNF_GRAMMAR.start == "rulelist"


def test_abnf_grammar_defines_the_x_d_b_prefix_letters_case_insensitively():
    """A marker class accepts both cases of its letter, in either order."""
    assert IrChr("X") in MARK_X
    assert IrChr("x") in MARK_X
