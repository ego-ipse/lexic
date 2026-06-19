"""Tests for lexic.parsing_2.reduce — Reducer bottom-up fold.

API changes:

- ``Reducer(...).reduce(tree)`` → ``Reducer(...).apply(tree)``.
  Every call site updated.

- ``normalize.is_synthetic_name(name)`` removed.
  Re-expressed as ``name.startswith(SYNTHETIC_PREFIX)``.

New symbols tested: ``ResolveChildren``, ``RESOLVE_CHILDREN``.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrArgs, IrJoin
from lexic.ir.base import IrCallable, IrNone, IrSelf, IrSeq, IrTuple
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2.engine import parse
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import (
    SYNTHETIC_PREFIX,
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)
from lexic.parsing_2.reduce import RESOLVE_CHILDREN, Reducer, ResolveChildren

# ── Helpers ───────────────────────────────────────────────────────────

_YIELD = IrJoin(parts=IrArgs(), separator=IrLiteral(""), empty=IrLiteral(""))
"""Concatenate reduced children — the string-yield body."""


def _leaf_tree(symbol: str, *chars: str) -> ParseTree:
    """A ParseTree whose kids are IrLiteral leaves."""
    return ParseTree(IrRuleRef(symbol), IrSeq(*(IrLiteral(c) for c in chars)))


def _reducer(*rows: tuple[str, IrSelf]) -> Reducer:
    """Build a Reducer from (rule_name, body) pairs."""
    dyads: tuple[IrTuple[IrRuleRef, IrSelf], ...] = tuple(
        IrTuple(IrRuleRef(name), body) for name, body in rows
    )
    return Reducer(reductions=IrMap(*dyads))


# ── Basic reduction ───────────────────────────────────────────────────


def test_reducer_joins_leaf_literals():
    """Reducer with _YIELD joins IrLiteral leaves into a string."""
    tree = _leaf_tree("letter", "h")
    reducer = _reducer(("letter", _YIELD))
    result = reducer.apply(tree)
    assert str(result) == "h"


def test_reducer_joins_multiple_leaves():
    """Reducer with _YIELD concatenates multiple IrLiteral leaves."""
    tree = _leaf_tree("word", "h", "i")
    reducer = _reducer(("word", _YIELD))
    result = reducer.apply(tree)
    assert str(result) == "hi"


def test_reducer_recurses_into_children():
    """Reducer reduces sub-trees before evaluating the parent."""
    letter_tree = _leaf_tree("letter", "x")
    word_tree = ParseTree(
        IrRuleRef("word"),
        IrSeq(letter_tree, letter_tree),
    )
    reducer = _reducer(("letter", _YIELD), ("word", _YIELD))
    result = reducer.apply(word_tree)
    assert str(result) == "xx"


def test_reducer_callable_body_receives_reduced_children():
    """An IrCallable body receives already-reduced children in nc."""
    collected: list[IrSelf] = []

    def capture(_d: IrSelf, _n: IrSelf, nc, /) -> IrLiteral:
        collected.extend(nc)
        return IrLiteral("".join(str(c) for c in nc))

    tree = _leaf_tree("s", "a", "b")
    reducer = _reducer(("s", IrCallable(capture)))
    result = reducer.apply(tree)
    assert len(collected) == 2
    assert str(result) == "ab"


# ── Missing reduction ─────────────────────────────────────────────────


def test_reducer_raises_on_missing_reduction():
    """A ParseTree whose symbol has no reduction raises UnsupportedConstructError."""
    tree = _leaf_tree("missing_rule", "x")
    reducer = Reducer(reductions=IrMap())
    with pytest.raises(UnsupportedConstructError):
        reducer.apply(tree)


# ── Synthetic-node splicing ───────────────────────────────────────────


def test_reducer_splices_synthetic_child_into_parent():
    """Synthetic-rule sub-trees are spliced: their children inline into the parent."""
    syn_name = f"{SYNTHETIC_PREFIX}rep_1"
    assert syn_name.startswith(SYNTHETIC_PREFIX)

    synthetic_child = ParseTree(IrRuleRef(syn_name), IrSeq(IrLiteral("a")))
    parent = ParseTree(IrRuleRef("s"), IrSeq(synthetic_child))
    reducer = _reducer(("s", _YIELD))
    result = reducer.apply(parent)
    assert str(result) == "a"


def test_reducer_splices_multiple_children_from_synthetic():
    """Multiple children from a synthetic node are all spliced into the parent."""
    syn_name = f"{SYNTHETIC_PREFIX}opt_1"
    synthetic_child = ParseTree(
        IrRuleRef(syn_name),
        IrSeq(IrLiteral("a"), IrLiteral("b")),
    )
    parent = ParseTree(IrRuleRef("s"), IrSeq(synthetic_child))
    reducer = _reducer(("s", _YIELD))
    result = reducer.apply(parent)
    assert str(result) == "ab"


def test_reducer_splices_recursive_synthetic():
    """Nested synthetic nodes are recursively spliced (children of children)."""
    syn2 = f"{SYNTHETIC_PREFIX}rep_2"
    syn1 = f"{SYNTHETIC_PREFIX}rep_1"
    inner_syn = ParseTree(IrRuleRef(syn2), IrSeq(IrLiteral("x")))
    outer_syn = ParseTree(IrRuleRef(syn1), IrSeq(inner_syn, IrLiteral("y")))
    parent = ParseTree(IrRuleRef("s"), IrSeq(outer_syn))
    reducer = _reducer(("s", _YIELD))
    result = reducer.apply(parent)
    assert str(result) == "xy"


def test_reducer_non_synthetic_child_not_spliced():
    """Non-synthetic sub-trees are reduced as normal, not spliced."""
    child = _leaf_tree("letter", "z")
    parent = ParseTree(IrRuleRef("word"), IrSeq(child))
    reducer = _reducer(("letter", _YIELD), ("word", _YIELD))
    result = reducer.apply(parent)
    assert str(result) == "z"


def test_reducer_literal_leaves_passed_through_without_reduction():
    """IrLiteral kids (terminal leaves) are passed as-is to the parent body."""

    def capture(_d: IrSelf, _n: IrSelf, nc, /) -> IrLiteral:
        # nc should contain the raw IrLiteral
        return nc[0]

    tree = _leaf_tree("s", "q")
    reducer = _reducer(("s", IrCallable(capture)))
    result = reducer.apply(tree)
    assert result == IrLiteral("q")


# ── ResolveChildren node ──────────────────────────────────────────────


def test_resolve_children_singleton_is_resolve_children_instance():
    """RESOLVE_CHILDREN is a ResolveChildren instance."""
    assert isinstance(RESOLVE_CHILDREN, ResolveChildren)


# ── Integration with normalize ────────────────────────────────────────


def test_reducer_with_normalized_quantified_grammar():
    """Reducer works correctly on a normalized quantified grammar (synthetic rules splice)."""
    # Grammar: s = 'a'* (nullable)
    rule = IrRule(
        "s", IrAlternation(IrSequence(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone))))
    )
    g_raw = IrAst(rules=IrSeq(rule), start="s")
    g = split_literals(desugar_quantifiers(flatten_groups(g_raw)))

    tree = parse(g, "aa")
    # Only 's' in the reduction table — synthetic rule spliced by the Reducer
    reducer = _reducer(("s", _YIELD))
    result = reducer.apply(tree)
    assert str(result) == "aa"
