"""Tests for lexic.parsing.earley.kernel.forest.fasttree — the unambiguous
parse's short path.

Exercised at scale (as the fallback discriminator) in
``tests/unit/lexic/parsing/earley/kernel/forest/test_ambiguity.py``; this
file targets ``FastTree.build``'s own contract directly: it succeeds on an
unambiguous handle, misses on an ambiguity point with ``choices=None``, and
resolves to a NAMED derivation when a choice is pinned.
"""

from __future__ import annotations

from lexic.ir import IrNone, IrRuleRef
from lexic.parsing.earley.kernel.forest.fasttree import (
    FastTree,
    first_tree,
    streamed_first,
)
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import ambiguity_points
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_handles,
    accept_node,
    to_chart,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.decider import LEFTMOST_LONGEST
from tests.unit.lexic.parsing.earley.kernel.forest.forest_helpers import (
    kernel_and_handle,
    twin_arm_grammar,
)

UNAMBIGUOUS = 'root ::= "a" mid "b"\nmid ::= "x" | "y"\n'
AMBIGUOUS_EXPR = 'e ::= e "+" e | "n"\n'


def test_build_returns_a_parse_tree_for_an_unambiguous_handle():
    """A plain unambiguous handle builds a real tree, not a fast-path miss."""
    kernel, handle = kernel_and_handle("axb", UNAMBIGUOUS, "fasttree-unambig")
    tree = FastTree(kernel, {}, LEFTMOST_LONGEST).build(handle)
    assert isinstance(tree, ParseTree)


def test_build_returns_irnone_at_an_ambiguity_point_with_choices_none():
    """``choices=None`` is the fast path's own contract: an ambiguity point
    is a miss, and the caller falls back to the trampolined enumeration."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "fasttree-miss")
    point = ambiguity_points(kernel, handle)[0]
    assert FastTree(kernel, None, LEFTMOST_LONGEST).build(point) is IrNone


def test_build_resolves_a_pinned_ambiguity_point_to_the_named_derivation():
    """Two distinct family indices at the same ambiguity point build two
    DIFFERENT trees — left- vs right-associative grouping of the same span."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "fasttree-pin")
    point = ambiguity_points(kernel, handle)[0]
    left = FastTree(kernel, {point: 0}, LEFTMOST_LONGEST).build(point)
    right = FastTree(kernel, {point: 1}, LEFTMOST_LONGEST).build(point)
    assert isinstance(left, ParseTree) and isinstance(right, ParseTree)
    assert left != right


def test_build_is_deterministic_for_the_same_handle_and_choices():
    """Two builds of the same handle under the same (empty) choices agree."""
    kernel, handle = kernel_and_handle("axb", UNAMBIGUOUS, "fasttree-deterministic")
    first = FastTree(kernel, {}, LEFTMOST_LONGEST).build(handle)
    second = FastTree(kernel, {}, LEFTMOST_LONGEST).build(handle)
    assert first == second


def test_a_fresh_fasttree_instance_starts_with_an_empty_memo():
    """A freshly constructed FastTree carries no built subtrees yet."""
    kernel, _handle = kernel_and_handle("axb", UNAMBIGUOUS, "fasttree-empty-memo")
    tree = FastTree(kernel, None, LEFTMOST_LONGEST)
    assert not tree.memo
    assert tree.choices is None


def _arm(tree: ParseTree) -> IrRuleRef:
    """Which production of the twin-arm root a derivation went through."""
    child = tree.kids[0]
    assert isinstance(child, ParseTree)
    return child.symbol


def test_first_tree_takes_the_first_handle_that_builds_in_the_order_given():
    """The reader keeps the caller's order: reversed handles, the other arm."""
    kernel = Kernel(compile_tables(twin_arm_grammar()), "x", record_links=True).run()
    handles = accept_handles(kernel)
    first = first_tree(kernel, handles, LEFTMOST_LONGEST)
    last = first_tree(kernel, handles[::-1], LEFTMOST_LONGEST)
    assert first is not None and last is not None
    assert (first.handle, _arm(first.tree)) == (handles[0], IrRuleRef("a"))
    assert (last.handle, _arm(last.tree)) == (handles[1], IrRuleRef("b"))


def test_first_tree_keeps_the_builds_memo_with_the_root_in_it():
    """The memo is the build's own: the root handle maps to the very tree."""
    kernel = Kernel(compile_tables(twin_arm_grammar()), "x", record_links=True).run()
    first = first_tree(kernel, accept_handles(kernel), LEFTMOST_LONGEST)
    assert first is not None
    assert first.memo[first.handle] is first.tree


def test_first_tree_is_none_when_no_handle_is_offered():
    """Nothing accepted, nothing built."""
    kernel = Kernel(compile_tables(twin_arm_grammar()), "z", record_links=True).run()
    assert first_tree(kernel, accept_handles(kernel), LEFTMOST_LONGEST) is None


def test_streamed_first_reads_the_chart_and_keeps_no_handles():
    """The decoded chart's first derivation, under the handle it is given, with
    the empty memo that tells a meaning comparison nothing was fast-built."""
    kernel = Kernel(compile_tables(twin_arm_grammar()), "x", record_links=True).run()
    handle = accept_handle(kernel)
    got = streamed_first(accept_node(kernel), to_chart(kernel), handle)
    assert got is not None
    assert (got.handle, got.memo, _arm(got.tree)) == (handle, {}, IrRuleRef("a"))
