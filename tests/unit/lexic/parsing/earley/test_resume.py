"""Unit tests for :mod:`lexic.parsing.earley.resume` — the resumable recognizer.

The soundness gate is differential: after any mark/extend/rollback history the
chart answers (accept, viability) exactly as a fresh parse of the same text —
including re-extending a rolled-back junction with a DIFFERENT character (the
gated-final-close edge the junction re-seed exists for).
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrSequence,
)
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.resume import ResumableKernel
from lexic.parsing.earley.tables import compile_tables
from lexic.parsing.earley.tokenscan import frontier_viable
from tests.unit.lexic.parsing.ir_fixtures import digits_plus_grammar, word_grammar


def _gated_pair() -> IrAst:
    """root = "ab" / "ac" — FIRST-gated sibling arms sharing a junction char."""
    rule = IrRule(
        "root",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))),
            IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("c"))),
        ),
    )
    return normalize(IrAst(rules=IrSeq(rule), start="root"))


def _fresh(tables, text: str) -> tuple[bool, bool]:
    """A fresh parse's (accepts, viable) answer for ``text``."""
    kernel = Kernel(tables, text).run()
    return kernel.accept >= 0, frontier_viable(kernel)


def _resumable(tables) -> ResumableKernel:
    """An empty-prefix resumable recognizer over ``tables``."""
    return ResumableKernel(tables, "", False).run()


@pytest.mark.parametrize(
    "grammar, words",
    [
        (_gated_pair(), ["ab", "ac", "ax", "b"]),
        (normalize(word_grammar()), ["ab", "a", "abc", "1a"]),
        (digits_plus_grammar(), ["7", "123", "12x"]),
    ],
)
def test_char_by_char_extension_matches_fresh_parse(grammar, words):
    """Extending one char at a time answers exactly like fresh whole parses."""
    tables = compile_tables(grammar)
    for word in words:
        kern = _resumable(tables)
        for k, char in enumerate(word):
            kern.extend(char)
            assert (kern.accept >= 0, frontier_viable(kern)) == _fresh(
                tables, word[: k + 1]
            ), word[: k + 1]


def test_rollback_then_different_char_through_the_same_junction():
    """The junction column stays char-independent: after extending 'b' off 'a'
    and rolling back, extending 'c' still finds its (previously gate-dropped)
    arm — the E6-1 re-seed invariant."""
    tables = compile_tables(_gated_pair())
    kern = _resumable(tables)
    kern.extend("a")
    mark = kern.mark()
    kern.extend("b")
    assert kern.accept >= 0
    kern.rollback(mark)
    assert kern.text == "a"
    kern.extend("c")
    assert kern.accept >= 0
    kern.rollback(mark)
    kern.extend("x")
    assert kern.accept < 0 and not frontier_viable(kern)


def test_multi_char_extend_equals_char_by_char():
    """extend("123") lands the same chart answers as three single extends."""
    tables = compile_tables(digits_plus_grammar())
    bulk = _resumable(tables)
    bulk.extend("123")
    stepped = _resumable(tables)
    for char in "123":
        stepped.extend(char)
    assert (bulk.accept >= 0, frontier_viable(bulk)) == (
        stepped.accept >= 0,
        frontier_viable(stepped),
    )
    assert bulk.text == stepped.text == "123"


def test_rollback_truncates_every_per_column_index():
    """rollback(mark) leaves exactly mark+1 columns in every per-parse index."""
    tables = compile_tables(digits_plus_grammar())
    kern = _resumable(tables)
    kern.extend("12")
    mark = kern.mark()
    kern.extend("34")
    kern.rollback(mark)
    st = kern.st
    for index in (kern.cols, st.seen, st.waiting, st.scannable, st.predicted, st.leo):
        assert len(index) == mark + 1


def test_extend_refuses_under_record_links():
    """extend() is recognition-only — the SPPF is parse-global."""
    tables = compile_tables(digits_plus_grammar())
    kern = ResumableKernel(tables, "", True).run()
    with pytest.raises(UnsupportedConstructError):
        kern.extend("1")


def test_extend_refuses_beyond_capacity():
    """Growing past the packing tier's capacity raises, never wraps."""
    tables = compile_tables(digits_plus_grammar(), 8)
    kern = ResumableKernel(tables, "", False).run()
    kern.extend("7" * 255)
    with pytest.raises(UnsupportedConstructError):
        kern.extend("7")
