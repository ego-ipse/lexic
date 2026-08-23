"""Tests for lexic.parsing.earley.kernel.forest.fasttree — the unambiguous
parse's short path.

Exercised at scale (as the fallback discriminator) in
``tests/unit/lexic/parsing/earley/kernel/forest/test_ambiguity.py``; this
file targets ``FastTree.build``'s own contract directly: it succeeds on an
unambiguous handle, misses on an ambiguity point with ``choices=None``, and
resolves to a NAMED derivation when a choice is pinned.
"""

from __future__ import annotations

from lexic.ir import IrNone
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import ambiguity_points
from tests.unit.lexic.parsing.earley.kernel.forest.forest_helpers import (
    kernel_and_handle,
)

UNAMBIGUOUS = 'root ::= "a" mid "b"\nmid ::= "x" | "y"\n'
AMBIGUOUS_EXPR = 'e ::= e "+" e | "n"\n'


def test_build_returns_a_parse_tree_for_an_unambiguous_handle():
    """A plain unambiguous handle builds a real tree, not a fast-path miss."""
    kernel, handle = kernel_and_handle("axb", UNAMBIGUOUS, "fasttree-unambig")
    tree = FastTree(kernel, {}).build(handle)
    assert isinstance(tree, ParseTree)


def test_build_returns_irnone_at_an_ambiguity_point_with_choices_none():
    """``choices=None`` is the fast path's own contract: an ambiguity point
    is a miss, and the caller falls back to the trampolined enumeration."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "fasttree-miss")
    point = ambiguity_points(kernel, handle)[0]
    assert FastTree(kernel, None).build(point) is IrNone


def test_build_resolves_a_pinned_ambiguity_point_to_the_named_derivation():
    """Two distinct family indices at the same ambiguity point build two
    DIFFERENT trees — left- vs right-associative grouping of the same span."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "fasttree-pin")
    point = ambiguity_points(kernel, handle)[0]
    left = FastTree(kernel, {point: 0}).build(point)
    right = FastTree(kernel, {point: 1}).build(point)
    assert isinstance(left, ParseTree) and isinstance(right, ParseTree)
    assert left != right


def test_build_is_deterministic_for_the_same_handle_and_choices():
    """Two builds of the same handle under the same (empty) choices agree."""
    kernel, handle = kernel_and_handle("axb", UNAMBIGUOUS, "fasttree-deterministic")
    first = FastTree(kernel, {}).build(handle)
    second = FastTree(kernel, {}).build(handle)
    assert first == second


def test_a_fresh_fasttree_instance_starts_with_an_empty_memo():
    """A freshly constructed FastTree carries no built subtrees yet."""
    kernel, _handle = kernel_and_handle("axb", UNAMBIGUOUS, "fasttree-empty-memo")
    tree = FastTree(kernel)
    assert not tree.memo
    assert tree.choices is None
