"""Tests for lexic.parsing_2.reduce — Reducer bottom-up fold.

API changes (old → new):

- ``Reducer(...).reduce(tree)`` → ``Reducer(...).apply(tree)``.
  Every call site updated.

- ``normalize.is_synthetic_name(name)`` removed.
  Re-expressed as ``name.startswith(SYNTHETIC_PREFIX)``.

- ``ResolveChildren`` / ``RESOLVE_CHILDREN`` (child resolution node)  →
  ``ResolveSource(node, ctx, reducer)`` trampoline cogen.
  ``test_resolve_children_singleton_is_resolve_children_instance`` is adapted
  into a behavioral test: ``list(Trampoline(ResolveSource(tree, ctx, reducer)))``
  yields the expected resolved child contributions.

New symbols: ``ReduceCtx``, ``ResolveSource``, ``ReduceSource`` (trampolined cogens).
``KEEP_REDUCED`` now threads ``nc`` — ``IrTuple(d.eval(d, n, nc))`` — so the
existing direct test using ``_Identity`` (which ignores nc) still passes.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrArgs, IrJoin
from lexic.ir.base import IrLambda, IrNone, IrSelf, IrSeq, IrTuple
from lexic.ir.mapping import IR_DEFAULT, IrMap
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
from lexic.parsing_2 import derivations, parse
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import (
    SYNTHETIC_PREFIX,
    desugar_quantifiers,
    flatten_groups,
    normalize,
    split_literals,
)
from lexic.parsing_2.reduce import (
    DROP,
    KEEP_RAW,
    KEEP_REDUCED,
    YIELD,
    ReduceCtx,
    Reducer,
    ResolveSource,
    Yield,
)
from lexic.parsing_2.trampoline import Trampoline

# ── Helpers ───────────────────────────────────────────────────────────

_YIELD = IrJoin(parts=IrArgs(), separator=IrLiteral(""), empty=IrLiteral(""))
"""Concatenate reduced children — the string-yield body."""


def _leaf_tree(symbol: str, *chars: str) -> ParseTree:
    """A ParseTree whose kids are IrLiteral leaves.

    :param symbol: The rule name for the tree's symbol.
    :param chars: The literal characters to use as leaf kids.
    :returns: A :class:`ParseTree` with :class:`IrLiteral` kids.
    """
    return ParseTree(IrRuleRef(symbol), IrSeq(*(IrLiteral(c) for c in chars)))


def _reducer(*rows: tuple[str, IrSelf]) -> Reducer:
    """Build a Reducer from (rule_name, body) pairs.

    :param rows: Pairs of ``(rule_name, body)`` to populate the reduction table.
    :returns: A :class:`Reducer` with those reductions.
    """
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
    """An IrLambda body receives already-reduced children in nc."""
    collected: list[IrSelf] = []

    def capture(_d: IrSelf, _n: IrSelf, nc, /) -> IrLiteral:
        collected.extend(nc)
        return IrLiteral("".join(str(c) for c in nc))

    tree = _leaf_tree("s", "a", "b")
    reducer = _reducer(("s", IrLambda(capture)))
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
    reducer = _reducer(("s", IrLambda(capture)))
    result = reducer.apply(tree)
    assert result == IrLiteral("q")


# ── ResolveSource cogen (adapted from ResolveChildren / RESOLVE_CHILDREN) ──
#
# Old: RESOLVE_CHILDREN was a ``ResolveChildren`` instance whose ``eval``
#      returned the resolved child contributions.
# New: ``ResolveSource(node, ctx, reducer)`` is a trampolined cogen; drive it
#      via ``list(Trampoline(ResolveSource(tree, ctx, reducer)))`` to get the
#      resolved child contribution elements.


def test_resolve_source_yields_literal_leaf_contributions():
    """ResolveSource yields each IrLiteral leaf as a raw contribution.

    Adapted from ``test_resolve_children_singleton_is_resolve_children_instance``:
    rather than checking a singleton type, we check the behavioral guarantee —
    a tree with two literal kids yields two raw contributions via Trampoline.
    """
    tree = _leaf_tree("s", "a", "b")
    reducer = _reducer(("s", _YIELD))
    ctx = ReduceCtx()
    contributions = list(Trampoline(ResolveSource(tree, ctx, reducer)))
    # Two IrLiteral leaves → two KEEP_RAW contributions (the leaves themselves)
    assert len(contributions) == 2
    assert contributions[0] == IrLiteral("a")
    assert contributions[1] == IrLiteral("b")


def test_resolve_source_drops_noise_children():
    """ResolveSource respects the noise policy: a DROP child contributes nothing.

    ``ws`` is mapped to ``DROP`` in the noise policy; ``letter`` uses the
    default ``KEEP_REDUCED`` (from ``IR_DEFAULT``), so the Reducer's default
    noise entry must be present.  After resolving, only the letter contribution
    arrives (ws is silently dropped).
    """
    # noise: ws → DROP, default → KEEP_REDUCED (mirrors the Reducer class default)
    noise = IrMap(
        IrTuple(IrRuleRef("ws"), DROP),
        IrTuple(IR_DEFAULT, KEEP_REDUCED),
    )
    reducer = Reducer(
        reductions=IrMap(IrTuple(IrRuleRef("letter"), _YIELD)),
        noise=noise,
    )
    ctx = ReduceCtx()

    ws_tree = _leaf_tree("ws", " ")
    letter_tree = _leaf_tree("letter", "x")
    parent = ParseTree(IrRuleRef("word"), IrSeq(letter_tree, ws_tree))

    contributions = list(Trampoline(ResolveSource(parent, ctx, reducer)))
    # ws is dropped; letter contributes one reduced element
    assert len(contributions) == 1


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


# ── DROP / KEEP_RAW / KEEP_REDUCED contribution bodies ───────────────


def test_drop_returns_empty_irtuple():
    """DROP contributes nothing — returns an empty IrTuple (flat-map: splice 0)."""
    n = IrLiteral("x")
    result = DROP.eval(IrNone, n, ())
    assert isinstance(result, IrTuple)
    assert len(result) == 0


def test_keep_raw_returns_irtuple_with_node_unchanged():
    """KEEP_RAW contributes the raw node — IrTuple(n), no dispatch."""
    n = IrLiteral("x")
    result = KEEP_RAW.eval(IrNone, n, ())
    assert isinstance(result, IrTuple)
    elements = list(result)
    assert len(elements) == 1
    assert elements[0] is n


def test_keep_reduced_dispatches_node_via_d():
    """KEEP_REDUCED contributes the reduced node — IrTuple(d.eval(d, n, nc))."""
    n = IrLiteral("x")

    class _Identity(IrSelf):
        """Minimal dispatcher: eval returns the node unchanged."""

        __slots__ = ()

        def eval(self, _d, m, _nc, /):
            return m

    result = KEEP_REDUCED.eval(_Identity(), n, ())
    assert isinstance(result, IrTuple)
    elements = list(result)
    assert len(elements) == 1
    assert elements[0] is n


def test_keep_raw_preserves_non_dispatch_semantics():
    """KEEP_RAW never calls d.eval — the node in the tuple is the same object."""
    n = IrLiteral("z")
    calls: list[object] = []

    class _Counting(IrSelf):
        """Records each eval call."""

        __slots__ = ()

        def eval(self, _d, m, _nc, /):
            calls.append(m)
            return m

    KEEP_RAW.eval(_Counting(), n, ())
    assert not calls  # KEEP_RAW must not invoke d.eval


# ── YIELD / Yield ─────────────────────────────────────────────────────


def test_yield_is_yield_instance():
    """YIELD is a Yield instance — the shared stateless subtree-text node."""
    assert isinstance(YIELD, Yield)


def test_yield_leaf_returns_str_of_leaf():
    """YIELD on a terminal leaf returns IrStr(str(n))."""
    n = IrLiteral("abc")
    reducer = Reducer(reductions=IrMap())
    result = YIELD.eval(reducer, n, ())
    assert str(result) == "abc"


def test_yield_tree_concatenates_kept_leaves():
    """YIELD concatenates all leaf characters in a tree with no dropped rules."""
    tree = _leaf_tree("word", "h", "e", "l", "l", "o")
    reducer = Reducer(reductions=IrMap())
    result = YIELD.eval(reducer, tree, ())
    assert str(result) == "hello"


def test_yield_skips_noise_sub_trees():
    """YIELD skips sub-trees whose rule the noise policy marks DROP."""
    noise = IrMap(IrTuple(IrRuleRef("ws"), DROP))
    ws_tree = ParseTree(IrRuleRef("ws"), IrSeq(IrLiteral(" ")))
    parent = ParseTree(
        IrRuleRef("word"), IrSeq(IrLiteral("a"), ws_tree, IrLiteral("b"))
    )
    reducer = Reducer(reductions=IrMap(), noise=noise)
    result = YIELD.eval(reducer, parent, ())
    assert str(result) == "ab"


# ── Reducer noise / literal params ────────────────────────────────────


def test_reducer_noise_drops_marked_children():
    """A Reducer with noise=IrMap(ws → DROP) excludes ws children from nc."""
    noise = IrMap(
        IrTuple(IrRuleRef("ws"), DROP),
        IrTuple(IrRuleRef("letter"), KEEP_REDUCED),
    )

    collected: list[IrSelf] = []

    def capture(_d, _n, nc, /):
        collected.extend(nc)
        return IrLiteral("".join(str(c) for c in nc))

    ws_tree = _leaf_tree("ws", " ")
    letter_tree = _leaf_tree("letter", "a")
    parent = ParseTree(IrRuleRef("word"), IrSeq(letter_tree, ws_tree, letter_tree))

    reductions: IrMap[IrRuleRef, IrSelf] = IrMap(
        IrTuple(IrRuleRef("word"), IrLambda(capture)),
        IrTuple(IrRuleRef("letter"), _YIELD),
    )
    reducer = Reducer(reductions=reductions, noise=noise)
    result = reducer.apply(parent)
    # ws is dropped — nc should contain only the two letter reductions
    assert len(collected) == 2
    assert str(result) == "aa"


def test_reducer_literal_drop_excludes_inline_terminals():
    """A Reducer with literal=DROP excludes inline terminal leaves from nc.

    The parent ``stmt`` has a semantic ``name`` sub-tree and an inline
    ``IrLiteral("=")`` terminal leaf.  With ``literal=DROP`` the terminal
    leaf must not appear in ``nc`` when the ``stmt`` body runs.
    """
    nc_received: list[IrSelf] = []

    def capture(_d, _n, nc, /):
        nc_received.extend(nc)
        return IrLiteral("ok")

    # Use YIELD (the real subtree-text node) so the name body reads raw text,
    # not nc (which would be empty when literal=DROP drops its leaf children).
    eq_leaf = IrLiteral("=")
    name_tree = _leaf_tree("name", "s")
    parent = ParseTree(IrRuleRef("stmt"), IrSeq(name_tree, eq_leaf))

    noise = IrMap(
        IrTuple(IrRuleRef("name"), KEEP_REDUCED),
    )
    reductions: IrMap[IrRuleRef, IrSelf] = IrMap(
        IrTuple(IrRuleRef("stmt"), IrLambda(capture)),
        IrTuple(IrRuleRef("name"), YIELD),
    )
    reducer = Reducer(reductions=reductions, noise=noise, literal=DROP)
    reducer.apply(parent)
    # The inline "=" literal is dropped by literal=DROP — only the reduced
    # name subtree arrives in nc.
    assert len(nc_received) == 1
    assert str(nc_received[0]) == "s"


# ── Reducer idempotency over derivations ──────────────────────────────


def test_reducer_over_derivations_matches_single_reduce():
    """For unambiguous input, reducing each derivation gives the same result as
    the single-derivation reduce — Reducer is idempotent over derivations()."""
    # Grammar: s = 'a'* (unambiguous)
    rule = IrRule(
        "s", IrAlternation(IrSequence(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone))))
    )
    g_raw = IrAst(rules=IrSeq(rule), start="s")
    g = split_literals(desugar_quantifiers(flatten_groups(g_raw)))

    reducer = _reducer(("s", _YIELD))
    single = reducer.apply(parse(g, "aa"))

    all_derivations = derivations(g, "aa")
    assert len(all_derivations) == 1  # unambiguous
    assert reducer.apply(all_derivations[0]) == single


# ── Depth-safety regression test ──────────────────────────────────────


def test_deep_reduce_does_not_crash():
    """parse+reduce on a 1500-char right-recursive input does not raise RecursionError.

    The S='a'* grammar desugars to right-recursive rules whose parse tree is
    ~1500 nodes deep.  The old recursive reducer crashed at ~1000 levels.
    This test runs on the main thread at the DEFAULT recursion limit; no
    ``sys.setrecursionlimit`` call.
    """
    rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)))),
    )
    g_raw = IrAst(rules=IrSeq(rule), start="S")
    g = normalize(g_raw)
    n = 1500
    tree = parse(g, "a" * n)
    reducer = _reducer(("S", _YIELD))
    result = reducer.apply(tree)
    assert str(result) == "a" * n
