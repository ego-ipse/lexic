"""Tests for lexic.compile.reduce.variant — recognition-only twins for dropped
reduction subtrees.

``elide_subtrees``'s collision-refusal and its role inside the full
derivation pipeline are also pinned end to end in
``tests/unit/lexic/compile/test_reduction.py``; this file targets
``reachable_rules`` and ``elide_subtrees`` directly.
"""

from __future__ import annotations

import pytest

from lexic.compile.reduce.variant import elide_subtrees, reachable_rules
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)


def _grammar() -> IrAst:
    return IrAst(
        IrSeq(
            IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("gap"))))),
            IrRule("gap", IrAlternation(IrSequence(IrItem(IrLiteral(" "))))),
            IrRule("other", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))),
        ),
        "root",
    )


def test_reachable_rules_includes_the_roots_and_their_transitive_refs():
    grammar = _grammar()
    assert reachable_rules(grammar, {"root"}) == frozenset({"root", "gap"})


def test_reachable_rules_stops_at_a_nonexistent_root():
    grammar = _grammar()
    assert reachable_rules(grammar, {"missing"}) == frozenset()


def test_reachable_rules_excludes_unreferenced_rules():
    grammar = _grammar()
    assert "other" not in reachable_rules(grammar, {"gap"})


def test_elide_subtrees_with_no_roots_returns_the_grammar_unchanged():
    grammar = _grammar()
    expanded, aliases = elide_subtrees(grammar, frozenset())
    assert expanded == grammar
    assert aliases == {}


def test_elide_subtrees_adds_skip_twins_and_reports_their_source_aliases():
    grammar = _grammar()
    expanded, aliases = elide_subtrees(grammar, frozenset({"gap"}))
    names = {str(rule.name) for rule in expanded.rules}
    assert "gap-sk" in names
    assert aliases == {"gap-sk": "gap"}


def test_elide_subtrees_leaves_unrelated_rules_untouched():
    """A rule outside the dropped closure keeps its original body, with no
    twin minted for it."""
    grammar = _grammar()
    expanded, _aliases = elide_subtrees(grammar, frozenset({"gap"}))
    names = {str(rule.name) for rule in expanded.rules}
    assert "other" in names
    assert "other-sk" not in names


def test_elide_subtrees_refuses_a_twin_name_collision():
    grammar = IrAst(
        IrSeq(
            IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("gap"))))),
            IrRule("gap", IrAlternation(IrSequence(IrItem(IrLiteral(" "))))),
            IrRule("gap-sk", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))),
        ),
        "root",
    )
    with pytest.raises(UnsupportedConstructError, match="'gap-sk'"):
        elide_subtrees(grammar, frozenset({"gap"}))
