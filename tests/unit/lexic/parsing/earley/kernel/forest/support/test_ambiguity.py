"""Tests for lexic.parsing.earley.kernel.forest.support.ambiguity — does a span
mean more than one thing?

The split-vs-arm distinction is exercised at scale on real json input in
``tests/unit/lexic/parsing/earley/kernel/forest/test_ambiguity.py`` (the
sibling module named identically at the parent directory — a decided split is
not an ambiguity); this file targets ``same_value``'s equality semantics and
``ambiguity_points``/``another_meaning`` directly, on small hand-built
grammars.
"""

from __future__ import annotations

import math

from lexic.ir import IrStr
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
    another_meaning,
    same_value,
)
from tests.unit.lexic.parsing.earley.kernel.forest.forest_helpers import (
    kernel_and_handle,
)

AMBIGUOUS_EXPR = 'e ::= e "+" e | "n"\n'


def test_same_value_is_type_aware_an_ir_leaf_and_its_bare_text_differ():
    """Bare ``==`` would call these equal (the IR wraps ``str``); type
    awareness is exactly what fixes that false positive."""
    assert not same_value(IrStr("a"), "a")


def test_same_value_treats_nan_as_equal_to_itself():
    """Two derivations always build two DISTINCT NaN objects — bare ``==``
    would call them different and wrongly flag an ambiguity."""
    assert same_value(math.nan, math.nan)


def test_same_value_compares_tuples_and_dicts_structurally():
    """Structural equality over tuples and dicts, mismatch on either shape or
    a differing value."""
    assert same_value((1, 2), (1, 2))
    assert not same_value((1, 2), (1, 3))
    assert same_value({"a": 1}, {"a": 1})
    assert not same_value({"a": 1}, {"a": 2})


def test_same_value_treats_a_type_with_no_eq_as_indistinguishable():
    """Declining to define equality is "cannot tell", which reads as no
    observable difference rather than a refusal."""
    assert same_value(object(), object())


def test_ambiguity_points_is_empty_for_an_unambiguous_grammar():
    """No key in the link table packs more than one family."""
    kernel, handle = kernel_and_handle(
        "axb", 'root ::= "a" mid "b"\nmid ::= "x" | "y"\n', "ambiguity-none"
    )
    assert ambiguity_points(kernel, handle) == []


def test_ambiguity_points_finds_a_multi_family_key_in_an_ambiguous_grammar():
    """A genuinely ambiguous expression grammar has at least one such key."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "ambiguity-found")
    assert ambiguity_points(kernel, handle)


def test_another_meaning_is_none_when_every_grouping_builds_the_same_value():
    """Every grouping of ``e ::= e "+" e | "n"`` spans the same TEXT length
    regardless of how it associates — a build function insensitive to
    grouping finds no other meaning."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "another-meaning-none")
    tree = FastTree(kernel, {}).build(handle)
    assert isinstance(tree, ParseTree)

    def build_span_length(_tree: ParseTree) -> int:
        """A build function insensitive to how the span is grouped."""
        return len(kernel.text)

    assert another_meaning(kernel, handle, build_span_length, tree) is None


def test_another_meaning_finds_a_differing_derivation_when_the_build_sees_shape():
    """A build function sensitive to the tree's own shape (its ``repr``) DOES
    see left- vs right-associative grouping as a different meaning."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "another-meaning-found")
    tree = FastTree(kernel, {}).build(handle)
    assert isinstance(tree, ParseTree)
    other = another_meaning(kernel, handle, repr, tree)
    assert isinstance(other, ParseTree)
    assert repr(other) != repr(tree)
