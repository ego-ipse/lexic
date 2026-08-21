"""Unit tests for :mod:`lexic.parsing.earley.resume` — the resumable recognizer.

The soundness gate is differential: after any mark/extend/rollback history the
chart answers (accept, viability) exactly as a fresh parse of the same text —
including re-extending a rolled-back junction with a DIFFERENT character (the
gated-final-close edge the junction re-seed exists for).
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAlternation, IrAst, IrItem, IrLiteral, IrRule, IrSeq, IrSequence
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ORIGIN_BITS
from lexic.parsing.earley.lexruns import recognition_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.resume import ResumableKernel
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
    return accept_item(kernel) >= 0, frontier_viable(kernel)


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
            assert (accept_item(kern) >= 0, frontier_viable(kern)) == _fresh(
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
    assert accept_item(kern) >= 0
    kern.rollback(mark)
    assert kern.text == "a"
    kern.extend("c")
    assert accept_item(kern) >= 0
    kern.rollback(mark)
    kern.extend("x")
    assert accept_item(kern) < 0 and not frontier_viable(kern)


def test_multi_char_extend_equals_char_by_char():
    """extend("123") lands the same chart answers as three single extends."""
    tables = compile_tables(digits_plus_grammar())
    bulk = _resumable(tables)
    bulk.extend("123")
    stepped = _resumable(tables)
    for char in "123":
        stepped.extend(char)
    assert (accept_item(bulk) >= 0, frontier_viable(bulk)) == (
        accept_item(stepped) >= 0,
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


# ── adversarial: the junction's edges ─────────────────────────────────────


def _spanning_literal() -> IrAst:
    """root = "a" "bcd" — a multi-char literal that a scan crosses in one jump."""
    rule = IrRule(
        "root",
        IrAlternation(IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("bcd")))),
    )
    return normalize(IrAst(rules=IrSeq(rule), start="root"))


def test_extend_across_a_literal_landing_past_the_junction() -> None:
    """A multi-char literal SPANS the old frontier: the scan starts at the
    re-opened junction column and lands several columns beyond it in one step.
    The chart must still answer exactly as a fresh parse."""
    tables = compile_tables(_spanning_literal())
    kernel = _resumable(tables)
    kernel.extend("a")  # frontier now at 1 — the junction
    kernel.extend("bcd")  # one literal scan from 1 straight to 4
    assert (accept_item(kernel) >= 0, frontier_viable(kernel)) == _fresh(tables, "abcd")


def test_extend_empty_string_is_a_no_op() -> None:
    """``extend("")`` changes nothing — text, columns and answers all hold."""
    tables = compile_tables(_gated_pair())
    kernel = _resumable(tables)
    kernel.extend("a")
    before = (kernel.text, len(kernel.cols), accept_item(kernel))
    kernel.extend("")
    assert (kernel.text, len(kernel.cols), accept_item(kernel)) == before
    assert len(kernel.cols) == len(kernel.text) + 1  # no orphan column appended


def test_mark_and_rollback_at_column_zero() -> None:
    """Rolling back to the empty prefix restores an extendable chart.

    NOT compared against ``_fresh(tables, "")``: a fresh empty parse seeds
    FIRST-gated on the ABSENT next char, so it reports the empty prefix
    non-viable even though every word extends it. The rolled-back chart has
    been topped up by the junction re-seed and reports the truthful answer,
    so the meaningful invariant is that re-extending from column 0 lands
    exactly where a fresh parse of the same text does.
    """
    tables = compile_tables(_gated_pair())
    kernel = _resumable(tables)
    start = kernel.mark()
    assert start == 0
    kernel.extend("ab")
    kernel.rollback(start)
    assert kernel.text == ""
    assert len(kernel.cols) == 1
    kernel.extend("ac")  # a DIFFERENT word, from the rolled-back start
    assert (accept_item(kernel) >= 0, frontier_viable(kernel)) == _fresh(tables, "ac")


def test_empty_prefix_viability_is_gated_not_wrong() -> None:
    """Pins the asymmetry the test above works around: a FRESH empty parse
    under-reports viability (its seeds are gated on an absent char), while a
    chart that has been extended and rolled back reports the truth."""
    tables = compile_tables(_gated_pair())
    assert not frontier_viable(Kernel(tables, "").run())
    kernel = _resumable(tables)
    kernel.extend("a")
    kernel.rollback(0)
    assert frontier_viable(kernel)


def test_re_extending_the_same_char_files_no_duplicate_items() -> None:
    """Rollback then re-extend the SAME char: the junction re-seed must not
    re-file what the gated pass already filed. Items are packed ints, so a
    duplicated dot-0 item is directly observable as a repeated value."""
    tables = compile_tables(_gated_pair())
    kernel = _resumable(tables)
    mark = kernel.mark()
    kernel.extend("a")
    kernel.rollback(mark)
    kernel.extend("a")  # the same char, through a re-opened column
    for column in range(len(kernel.text) + 1):
        items = kernel.cols[column]
        assert len(items) == len(set(items)), (column, items)
    assert (accept_item(kernel) >= 0, frontier_viable(kernel)) == _fresh(tables, "a")


def test_extend_refuses_run_collapsed_tables() -> None:
    """Maximal munch and incremental extension are incompatible: a run terminal
    takes the MAXIMAL run, whose extent depends on input not yet appended, so a
    committed run could never grow. ``extend`` refuses loudly rather than
    silently under-parsing (extending "12" then "34" over run-collapsed tables
    would fail to accept "1234", which a fresh parse accepts)."""
    tables = recognition_tables(digits_plus_grammar(), ORIGIN_BITS)
    kernel = ResumableKernel(tables, "", False).run()
    with pytest.raises(UnsupportedConstructError, match="run-collapsed"):
        kernel.extend("12")


def test_extend_over_plain_tables_handles_the_same_run_grammar() -> None:
    """The same grammar WITHOUT run collapsing extends correctly — the refusal
    above is about the collapsed tables, not about runs in the language."""
    tables = compile_tables(digits_plus_grammar())
    kernel = _resumable(tables)
    kernel.extend("12")
    kernel.extend("34")
    assert (accept_item(kernel) >= 0, frontier_viable(kernel)) == _fresh(tables, "1234")
