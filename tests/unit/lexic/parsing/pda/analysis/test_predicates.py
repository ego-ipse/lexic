"""Tests for lexic.parsing.pda.analysis.predicates — per-node predicates and
their dispatch tables.

``FIRST``/``HARD``/``FOLLOW_FEED``/``SEQ_ATOM`` need a live ``GrammarAnalysis``
to drive them and are exercised through it in
``tests/unit/lexic/parsing/pda/analysis/test_analysis.py``; this file targets
the two tables usable standalone: ``nullable_names`` (self-contained, its own
fixpoint solver) and ``STOPSET_ATOM`` (a pure per-type predicate needing no
dispatcher context).
"""

from __future__ import annotations

from lexic.ir import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.pda.analysis.predicates import STOPSET_ATOM, nullable_names


def test_nullable_names_finds_an_empty_literal_arm():
    """A rule whose sole arm is the empty literal derives the empty string."""
    rules = [IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral("")))))]
    assert nullable_names(rules) == frozenset({"r"})


def test_nullable_names_excludes_a_rule_with_only_non_empty_arms():
    """A rule with no all-nullable arm is not in the result."""
    rules = [IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))]
    assert nullable_names(rules) == frozenset()


def test_nullable_names_an_optional_item_makes_its_arm_nullable():
    """A ``lo == 0`` item makes its whole arm nullable even with non-empty text."""
    rules = [
        IrRule(
            "r",
            IrAlternation(IrSequence(IrItem(IrLiteral("x"), IrQuantifier(0, 1)))),
        )
    ]
    assert nullable_names(rules) == frozenset({"r"})


def test_nullable_names_propagates_through_a_ruleref_chain():
    """``root`` is nullable because ``mid`` is, transitively — the fixpoint's
    own reason to exist over a one-pass check."""
    rules = [
        IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("mid"))))),
        IrRule("mid", IrAlternation(IrSequence(IrItem(IrLiteral(""))))),
    ]
    assert nullable_names(rules) == frozenset({"root", "mid"})


def test_nullable_names_any_arm_nullable_makes_the_whole_alternation_nullable():
    """One nullable arm among several non-nullable ones is enough."""
    rules = [
        IrRule(
            "r",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("x"))),
                IrSequence(IrItem(IrLiteral(""))),
            ),
        )
    ]
    assert nullable_names(rules) == frozenset({"r"})


def test_stopset_atom_is_true_only_for_a_single_char_loop_atom():
    """Only a char class is a single-char loop atom — a literal or ref is not."""
    charclass = IrCharClass(IrChr("a"))
    assert STOPSET_ATOM.resolve(charclass).eval(None, charclass, ()) is True

    literal = IrLiteral("x")
    assert STOPSET_ATOM.resolve(literal).eval(None, literal, ()) is False

    ref = IrRuleRef("r")
    assert STOPSET_ATOM.resolve(ref).eval(None, ref, ()) is False
