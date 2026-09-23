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

import pytest

from lexic.compile import compile_from_path
from lexic.ir import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.gates.windows import (
    END,
    MORE,
    FollowWindows,
    windows_of,
)
from lexic.parsing.pda.core.charsets import CharSet
from tests.paths import GROUND_TRUTH

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


def test_site_windows_keeps_each_reference_apart_and_unions_to_follow():
    """``root ::= "(" mid ")" | mid ";"``: one window set per reference, and
    their union is ``mid``'s FOLLOW."""
    paren = IrSequence(
        IrItem(IrLiteral("(")), IrItem(IrRuleRef("mid")), IrItem(IrLiteral(")"))
    )
    semi = IrSequence(IrItem(IrRuleRef("mid")), IrItem(IrLiteral(";")))
    rules = {
        "root": IrRule("root", IrAlternation(paren, semi)),
        "mid": IrRule("mid", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))),
    }
    fw = FollowWindows(rules, "root", 2)
    sites = fw.site_windows("mid")
    assert [windows_of(site) for site in sites] == [
        ((CharSet.from_chars(")"),),),
        ((CharSet.from_chars(";"),),),
    ]
    assert set().union(*sites) == fw.follow["mid"]
    assert fw.site_windows("root") == [{((), END)}]


def _follow_2(stem: str) -> FollowWindows:
    """FOLLOW\\ :sub:`2` over a ground-truth grammar, lifted as the analysis
    sees it."""
    grammar = lift_optional_nullables(
        compile_from_path(GROUND_TRUTH / stem).codegen_grammar
    )
    return FollowWindows({str(r.name): r for r in grammar.rules}, str(grammar.start), 2)


def test_an_empty_tail_is_the_fixpoints_bottom_not_the_end_of_input():
    """``term`` is always followed by something in arithmetic.gbnf: the input
    never ends right after it. Early in the fixpoint its tail is still empty,
    and reading that as "may end here" left a false end window for good. The
    start rule keeps its real one."""
    fw = _follow_2("arithmetic.gbnf")
    assert ((), END) not in fw.follow["term"]
    assert ((), END) in fw.follow[fw.start]


PINNED_ENDS: dict[str, int] = {
    "arithmetic.ebnf": 1,
    "arithmetic.gbnf": 1,
    "json.abnf": 19,
    "json.ebnf": 19,
    "json.gbnf": 19,
    "json_arr.gbnf": 1,
    "json_ws.gbnf": 2,
    "vyx.gbnf": 50,
}
"""Rules other than the start whose FOLLOW\\ :sub:`2` may end the input. Each is
a rule that really can end it; the fixpoint once held 7, 7, 20, 20, 20, 8, 7
and 73 here, the rest being the empty-tail pass-through."""


@pytest.mark.parametrize("stem", sorted(PINNED_ENDS))
def test_only_rules_that_can_end_the_input_hold_an_end_window(stem: str):
    """The per-grammar count of end windows, pinned where the false ones went."""
    fw = _follow_2(stem)
    ends = [n for n, found in fw.follow.items() if ((), END) in found and n != fw.start]
    assert len(ends) == PINNED_ENDS[stem]
