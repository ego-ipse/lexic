"""Tests for ir/order.py — RuleOrder: start-first, breadth-first-by-edges,
unreached-rules-alphabetical-last."""

from __future__ import annotations

from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.order import RuleOrder, order_by_refs


def rule(name: str, *refs: str) -> IrRule:
    """A rule whose body references ``refs``, in the given order, plus a literal tail."""
    items = [IrItem(IrRuleRef(ref)) for ref in refs]
    items.append(IrItem(IrLiteral("x")))
    return IrRule(name, IrSequence(*items))


# ── RuleOrder.ordered() — the base class over a supplied edge relation ────


def test_ordered_places_start_first():
    """The start rule is always first, regardless of input order."""
    order = RuleOrder(["a", "b", "start"], "start", lambda _n: []).ordered()
    assert order[0] == "start"


def test_ordered_is_breadth_first_over_edges():
    """Rules reachable from start appear in breadth-first (level) order."""
    edges = {"start": ["a", "b"], "a": ["c"], "b": ["d"]}
    order = RuleOrder(
        ["d", "c", "b", "a", "start"], "start", lambda n: edges.get(n, [])
    ).ordered()
    # level 0: start; level 1: a, b (edge order); level 2: c, d
    assert order == ["start", "a", "b", "c", "d"]


def test_ordered_unreached_rules_are_last_and_alphabetical():
    """A rule the BFS never reaches from start is appended, sorted alphabetically."""
    edges = {"start": ["a"]}
    order = RuleOrder(
        ["zeta", "start", "a", "beta"], "start", lambda n: edges.get(n, [])
    ).ordered()
    assert order == ["start", "a", "beta", "zeta"]


def test_ordered_deduplicates_a_rule_reached_by_multiple_edges():
    """A rule reachable via more than one edge appears exactly once."""
    edges = {"start": ["a", "b"], "a": ["shared"], "b": ["shared"]}
    order = RuleOrder(
        ["shared", "b", "a", "start"], "start", lambda n: edges.get(n, [])
    ).ordered()
    assert order.count("shared") == 1
    assert order == ["start", "a", "b", "shared"]


def test_ordered_ignores_an_edge_to_an_unknown_name():
    """An edge pointing outside the supplied name set is not followed."""
    edges = {"start": ["ghost", "a"]}
    order = RuleOrder(["start", "a"], "start", lambda n: edges.get(n, [])).ordered()
    assert order == ["start", "a"]


def test_ordered_start_not_in_names_still_orders_the_rest():
    """A start name absent from the rule set falls back to pure BFS-less alphabetical."""
    order = RuleOrder(["b", "a"], "missing-start", lambda _n: []).ordered()
    assert order == ["a", "b"]


# ── RuleOrder.ordered_parents_first() — the parent-edge policy ────────────


def test_parents_first_emits_a_parent_before_its_subclass():
    """A rule pointing at its parent lands after the parent, wherever it starts."""
    edges = {"child": ["parent"]}
    order = RuleOrder(
        ["child", "parent"], "child", lambda n: edges.get(n, [])
    ).ordered_parents_first()
    assert order == ["parent", "child"]


def test_parents_first_seeds_start_chain_then_input_order():
    """Start's ancestry leads; everything else keeps input order."""
    edges = {"start": ["base"], "arm": ["alt"]}
    order = RuleOrder(
        ["zeta", "start", "arm", "alt", "base"], "start", lambda n: edges.get(n, [])
    ).ordered_parents_first()
    assert order == ["base", "start", "zeta", "alt", "arm"]


def test_parents_first_keeps_input_order_without_edges():
    """With no edges the input order survives untouched (start hoisted)."""
    order = RuleOrder(
        ["b", "a", "start"], "start", lambda _n: []
    ).ordered_parents_first()
    assert order == ["start", "b", "a"]


def test_parents_first_ignores_an_edge_to_an_unknown_name():
    """An ancestor outside the name set (e.g. GrammarModel) is not emitted."""
    edges = {"a": ["ghost"]}
    order = RuleOrder(["a"], "a", lambda n: edges.get(n, [])).ordered_parents_first()
    assert order == ["a"]


def test_parents_first_terminates_on_an_edge_cycle():
    """A parent cycle emits each participant exactly once."""
    edges = {"a": ["b"], "b": ["a"]}
    order = RuleOrder(
        ["a", "b"], "a", lambda n: edges.get(n, [])
    ).ordered_parents_first()
    assert sorted(order) == ["a", "b"]


def test_parents_first_terminates_on_a_three_node_cycle():
    """A longer cycle (a -> b -> c -> a) still emits each name exactly once."""
    edges = {"a": ["b"], "b": ["c"], "c": ["a"]}
    order = RuleOrder(
        ["a", "b", "c"], "a", lambda n: edges.get(n, [])
    ).ordered_parents_first()
    assert sorted(order) == ["a", "b", "c"]
    assert len(order) == 3


def test_parents_first_visits_every_listed_ancestor_before_the_child():
    """A node with more than one declared ancestor waits on all of them."""
    edges = {"c": ["a", "b"]}
    order = RuleOrder(
        ["c", "a", "b"], "c", lambda n: edges.get(n, [])
    ).ordered_parents_first()
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("c")


def test_parents_first_is_deterministic_across_repeated_calls():
    """Calling ordered_parents_first() twice on the same instance agrees."""
    edges = {"start": ["base"], "arm": ["alt"]}
    order = RuleOrder(
        ["zeta", "start", "arm", "alt", "base"], "start", lambda n: edges.get(n, [])
    )
    assert order.ordered_parents_first() == order.ordered_parents_first()


def test_parents_first_shared_parent_emits_once_before_both_children():
    """Two subclasses of one parent both land after it; the parent appears once."""
    edges = {"x": ["base"], "y": ["base"]}
    order = RuleOrder(
        ["x", "y", "base"], "x", lambda n: edges.get(n, [])
    ).ordered_parents_first()
    assert order == ["base", "x", "y"]


# ── order_by_refs / RuleOrder.by_refs — the ref-edge policy ───────────────


def test_by_refs_orders_start_first_then_reference_order():
    """Rules reorder start-first, breadth-first by IrRuleRef occurrence."""
    ast = IrAst(
        IrSeq(rule("unrelated"), rule("b"), rule("root", "b")),
        "root",
    )
    result = order_by_refs(ast)
    assert [rule.name for rule in result.rules] == ["root", "b", "unrelated"]


def test_by_refs_uses_body_order_for_the_tie_break():
    """When a rule references two others, they appear in body (first-seen) order."""
    ast = IrAst(
        IrSeq(rule("second"), rule("first"), rule("root", "second", "first")),
        "root",
    )
    result = order_by_refs(ast)
    assert [rule.name for rule in result.rules] == ["root", "second", "first"]


def test_by_refs_unreferenced_rules_are_last_alphabetical():
    """Rules never referenced from start end up last, alphabetically sorted."""
    ast = IrAst(
        IrSeq(rule("zeta"), rule("alpha"), rule("root")),
        "root",
    )
    result = order_by_refs(ast)
    assert [rule.name for rule in result.rules] == ["root", "alpha", "zeta"]


def test_by_refs_preserves_start_name():
    """Reordering never changes the AST's start-rule name."""
    ast = IrAst(IrSeq(rule("b"), rule("a")), "a")
    result = order_by_refs(ast)
    assert result.start == "a"


def test_by_refs_only_first_occurrence_of_a_repeated_ref_counts():
    """A rule referenced more than once by the same body still orders once, at first mention."""
    ast = IrAst(
        IrSeq(rule("shared"), rule("root", "shared", "shared")),
        "root",
    )
    result = order_by_refs(ast)
    assert [rule.name for rule in result.rules] == ["root", "shared"]


def test_by_refs_is_a_noop_on_an_already_ordered_ast():
    """Reordering an AST already in canonical order returns an equal AST."""
    ast = IrAst(IrSeq(rule("root", "b"), rule("b")), "root")
    assert order_by_refs(ast) == ast


def test_by_refs_collects_edges_distinct_in_body_order():
    """Ref-edges drive the order first-seen, duplicates ignored (the deleted
    ``refs_in_order`` wrapper's contract, kept pinned on ``by_refs`` itself)."""
    ast = IrAst(IrSeq(rule("root", "b", "a", "b"), rule("a"), rule("b")), "root")
    assert [rule.name for rule in order_by_refs(ast).rules] == ["root", "b", "a"]
