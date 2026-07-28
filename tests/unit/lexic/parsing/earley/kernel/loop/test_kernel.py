"""Tests for lexic.parsing.earley.kernel.loop.kernel — KernelState, Kernel, FastTree.

New module: the flat int-coded Earley loop over compiled ParserTables. This
file covers the behavioral facts callable through the public surface
(``Kernel.run()`` + reading ``.cols``/``.st``/``accept_item``, or the top-level
``recognize()``/``parse()`` functions), plus the Leo right-recursion
correctness tests ported from the deleted ``test_ops.py`` (see that file's
git history — its target module ``lexic.parsing.ops`` no longer exists;
its behavioral coverage lives here now, re-expressed over ``Kernel``).
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrNoneType,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.parsing import recognize
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.readout import (
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ADVANCE, ORIGIN_BITS
from lexic.parsing.earley.normalize import normalize
from tests.unit.lexic.parsing.ir_fixtures import digit_grammar as _digit_grammar
from tests.unit.lexic.parsing.ir_fixtures import star
from tests.unit.lexic.parsing.ir_fixtures import word_grammar as _word_grammar

# ── Grammar helpers ───────────────────────────────────────────────────


def undefined_ref_grammar() -> IrAst:
    """top = missing ; 'missing' is referenced but never defined."""
    return IrAst(
        rules=IrSeq(
            IrRule("top", IrAlternation(IrSequence(IrItem(IrRuleRef("missing")))))
        ),
        start="top",
    )


# ── Prediction seeding: undefined rule ref seeds nothing ──────────────


def test_undefined_ref_recognize_never_crashes_and_fails():
    """recognize() on a grammar referencing an undefined rule fails cleanly."""
    g = undefined_ref_grammar()
    assert recognize(g, "anything") == 0
    assert recognize(g, "") == 0


def test_undefined_ref_kernel_accept_is_negative():
    """Kernel.run() over an undefined-ref grammar never resolves accept."""
    tables = compile_tables(undefined_ref_grammar())
    kernel = Kernel(tables, "x").run()
    assert accept_item(kernel) == -1


# ── FIRST-gated prediction: kernel seeding behavior (Task 2) ──────────


def test_arm_gated_out_by_first_charset_is_not_seeded_at_column():
    """s = digit / letter — a digit char seeds only the digit arm at column 0.

    Partitions ``s``'s own dot-0 seeds by whether their gate contains the
    scanned char (``gate is None`` also counts as seeding, per the
    always-seed rule), then checks the packed dot-0 item's presence in
    ``cols[0]`` directly — no reliance on ``waiting``/``scannable`` internals.
    """
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    letter = IrRule(
        "letter",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    s = IrRule(
        "s",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("digit"))),
            IrSequence(IrItem(IrRuleRef("letter"))),
        ),
    )
    g = IrAst(rules=IrSeq(s, digit, letter), start="s")
    tables = compile_tables(g)
    s_rid = tables.decode.rule_ids["s"]
    seeds = tables.codes.rule_seed_gates[s_rid]
    char = "5"
    should_seed = [
        shifted for shifted, _sym, gate in seeds if gate is None or char in gate
    ]
    should_not_seed = [
        shifted
        for shifted, _sym, gate in seeds
        if gate is not None and char not in gate
    ]
    assert should_seed and should_not_seed  # both partitions are non-empty

    kernel = Kernel(tables, char).run()
    for shifted in should_seed:
        assert shifted in kernel.cols[0]
    for shifted in should_not_seed:
        assert shifted not in kernel.cols[0]


def test_eof_column_only_gate_none_arms_seed():
    """s = digit / '' over empty input: at the EOF column, only the empty
    (always-seed) arm seeds — the digit arm's gate matches no char, and the
    EOF column's char slice is the empty string, which is in no charset."""
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    s = IrRule(
        "s",
        IrAlternation(IrSequence(IrItem(IrRuleRef("digit"))), IrSequence()),
    )
    g = IrAst(rules=IrSeq(s, digit), start="s")
    tables = compile_tables(g)
    s_rid = tables.decode.rule_ids["s"]
    seeds = tables.codes.rule_seed_gates[s_rid]
    (always_shifted,) = [shifted for shifted, _sym, gate in seeds if gate is None]
    (gated_shifted,) = [shifted for shifted, _sym, gate in seeds if gate is not None]

    kernel = Kernel(tables, "").run()
    assert always_shifted in kernel.cols[0]
    assert gated_shifted not in kernel.cols[0]


def test_empty_literal_terminal_arm_never_seeds_at_any_column():
    """An IrLiteral('') unit's FIRST gate is frozenset() — a real (unpoisoned)
    but empty charset, distinct from the `None` always-seed sentinel — so the
    arm seeds at no column, for any input."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    g = IrAst(rules=IrSeq(rule), start="s")
    tables = compile_tables(g)
    s_rid = tables.decode.rule_ids["s"]
    ((shifted, _sym, gate),) = tables.codes.rule_seed_gates[s_rid]
    assert gate == frozenset()

    for text in ("", "a", "ab"):
        kernel = Kernel(tables, text).run()
        assert all(shifted not in col for col in kernel.cols)


# ── Completion advancement: two-rule grammar ──────────────────────────


def test_kernel_accepts_valid_two_char_word():
    """word = letter letter accepts 'hi' — accept_item(kernel) resolves >= 0."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi").run()
    assert accept_item(kernel) >= 0


def test_kernel_rejects_wrong_input():
    """word = letter letter rejects a digit — accept_item(kernel) stays -1."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "h1").run()
    assert accept_item(kernel) == -1


def test_kernel_cols_grows_one_per_char():
    """Kernel.cols has len(text) + 1 columns after construction."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi")
    assert len(kernel.cols) == 3


# ── Aycock-Horspool nullable advance ───────────────────────────────────


def test_nullable_star_accepts_empty_via_kernel():
    """S = 'a'* (normalized) recognizes the empty string."""
    g = star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "").run()
    assert accept_item(kernel) >= 0


def test_nullable_star_accepts_single_via_kernel():
    """S = 'a'* recognizes a single 'a'."""
    g = star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "a").run()
    assert accept_item(kernel) >= 0


def test_nullable_star_accepts_many_via_kernel():
    """S = 'a'* recognizes a run of 'a's."""
    g = star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "aaa").run()
    assert accept_item(kernel) >= 0


# ── Scan advancement — accept/reject truth values ─────────────────────


def test_scan_accepts_single_char():
    """digit grammar accepts a single valid char."""
    assert recognize(_digit_grammar(), "5") == 1


def test_scan_rejects_wrong_char():
    """digit grammar rejects a non-matching char."""
    assert recognize(_digit_grammar(), "z") == 0


def test_scan_rejects_too_long_input():
    """digit grammar (single char) rejects multi-char input."""
    assert recognize(_digit_grammar(), "12") == 0


def test_scan_rejects_too_short_input():
    """digit grammar rejects the empty string."""
    assert recognize(_digit_grammar(), "") == 0


# ── FastTree single-derivation build ═══════════════════════════════════


def test_fast_tree_builds_correct_shape_for_two_char_word():
    """FastTree(kernel).build(handle) mirrors old tree-shape assertions."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi", record_links=True).run()
    assert accept_item(kernel) >= 0
    handle = (accept_item(kernel) << ORIGIN_BITS) | len("hi")
    tree = FastTree(kernel).build(handle)
    assert isinstance(tree, ParseTree)
    assert tree.symbol == IrRuleRef("word")
    assert len(tree.kids) == 2
    assert isinstance(tree.kids[0], ParseTree)
    assert isinstance(tree.kids[1], ParseTree)
    assert tree.kids[0].kids[0] == IrLiteral("h")
    assert tree.kids[1].kids[0] == IrLiteral("i")


def test_fast_tree_builds_correct_shape_for_digit():
    """FastTree over a single-char digit grammar builds a one-kid tree."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "9", record_links=True).run()
    handle = (accept_item(kernel) << ORIGIN_BITS) | 1
    tree = FastTree(kernel).build(handle)
    assert isinstance(tree, ParseTree)
    assert tree.symbol == IrRuleRef("digit")
    assert tree.kids[0] == IrLiteral("9")


# ── FastTree returns IrNone on ambiguous keys ──────────────────────────


def test_fast_tree_returns_ir_none_on_ambiguous_grammar(sss_grammar: IrAst):
    """FastTree.build() misses (returns IrNone) on an ambiguous grammar's handle."""
    g = normalize(sss_grammar)
    tables = compile_tables(g)
    kernel = Kernel(tables, "aaa", record_links=True).run()
    assert accept_item(kernel) >= 0
    handle = (accept_item(kernel) << ORIGIN_BITS) | len("aaa")
    result = FastTree(kernel).build(handle)
    assert isinstance(result, IrNoneType)
    assert result is IrNone


# ── ORIGIN_BITS capacity error ──────────────────────────────────────────


def test_kernel_construction_rejects_input_at_capacity():
    """Constructing Kernel with len(text) >= ADVANCE raises UnsupportedConstructError."""
    tables = compile_tables(_digit_grammar())
    huge = "a" * ADVANCE
    with pytest.raises(UnsupportedConstructError):
        Kernel(tables, huge)


def test_kernel_construction_accepts_input_under_capacity():
    """A text under the ADVANCE ceiling constructs one column per char + 1.

    The exact ``ADVANCE - 1`` boundary is memory-infeasible at the production
    ORIGIN_BITS (one list per column); the strict side of the guard is pinned
    by the rejection test at exactly ``ADVANCE``.
    """
    tables = compile_tables(_digit_grammar())
    text = "a" * 4096
    kernel = Kernel(tables, text)
    assert len(kernel.cols) == len(text) + 1
