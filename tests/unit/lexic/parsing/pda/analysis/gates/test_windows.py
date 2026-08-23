"""Tests for lexic.parsing.pda.analysis.gates.windows — the FIRST_k / FOLLOW_k
window computation.

``KWindowFirst``, ``collide``/``separable`` and ``extend_follow`` are already
exhaustively pinned (against a real fixed-review regression) in
``tests/unit/lexic/parsing/pda/analysis/gates/test_kwindow.py``, which reads
this module's own exports directly; this file targets ``windows_of``'s
dedup/sort contract and ``FollowWindows``'s EOF seeding on a small hand-built
grammar.
"""

from __future__ import annotations

from lexic.ir import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.pda.analysis.gates.windows import (
    END,
    MORE,
    FollowWindows,
    windows_of,
)
from lexic.parsing.pda.core.charsets import CharSet

A = CharSet.from_chars("a")
B = CharSet.from_chars("b")


def test_windows_of_drops_the_end_more_unk_tag():
    """The returned windows carry no END/MORE/UNK tag."""
    prefs = {((A,), END), ((B,), MORE)}
    windows = windows_of(prefs)
    assert all(isinstance(w, tuple) for w in windows)
    assert (A,) in windows and (B,) in windows


def test_windows_of_deduplicates_identical_windows_across_distinct_tags():
    """Two prefixes with the same window but different tags collapse to one
    entry — the tag was never part of the gate spec's identity."""
    prefs = {((A,), END), ((A,), MORE)}
    assert windows_of(prefs) == ((A,),)


def test_windows_of_is_deterministically_sorted():
    """Repeat calls over the same set produce the identical ordering."""
    prefs = {((B,), END), ((A,), END)}
    windows = windows_of(prefs)
    assert windows == windows_of(prefs)  # stable across calls
    assert len(windows) == 2


def test_follow_windows_seeds_the_start_rule_with_end_at_epsilon():
    """The start rule's FOLLOW is seeded with the EOF-at-epsilon prefix."""
    rules = {
        "root": IrRule("root", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))),
    }
    fw = FollowWindows(rules, "root", 2)
    assert fw.follow["root"] == {((), END)}


def test_follow_windows_propagates_the_continuation_past_a_referenced_rule():
    """``root ::= mid "y"``; ``mid``'s FOLLOW gains the ``"y"`` continuation."""
    rules = {
        "root": IrRule(
            "root",
            IrAlternation(IrSequence(IrItem(IrRuleRef("mid")), IrItem(IrLiteral("y")))),
        ),
        "mid": IrRule("mid", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))),
    }
    fw = FollowWindows(rules, "root", 2)
    windows = windows_of(fw.follow["mid"])
    assert any(win and str(win[0]) == str(CharSet.from_chars("y")) for win in windows)
