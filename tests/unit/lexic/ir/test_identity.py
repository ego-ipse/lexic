"""Tests for lexic.ir.identity: the census of a value's graph."""

from __future__ import annotations

import pathlib

import pytest

from lexic.compile import compile_from_path, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import (
    IrAction,
    IrAst,
    IrLambda,
    IrLiteral,
    IrMap,
    IrNone,
    IrSelf,
    IrStr,
    IrTuple,
    IrTypeMap,
    census,
    field_children,
    unspellable,
)
from tests.paths import GROUND_TRUTH


@pytest.fixture(name="json_ast", scope="module")
def json_ast_fixture() -> IrAst:
    """The ground-truth JSON grammar, parsed — a real graph to census."""
    text = pathlib.Path(GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    return parse_grammar(text, GBNF_FLAVOUR)


# ── the child definition ──────────────────────────────────────────────


def test_field_children_are_the_node_valued_elements() -> None:
    """A node's children are its field tuple's nodes — and nothing else."""
    leaf = IrLiteral("a")
    assert field_children(IrTuple(leaf, IrNone)) == (leaf, IrNone)


def test_a_scalar_has_no_children() -> None:
    """A value leaf IS its payload, so it carries nothing."""
    assert not field_children(IrLiteral("abc"))


def test_a_maps_entries_are_its_children() -> None:
    """A table's content IS its entries — each value under its own key.

    The map's payload is a dict rather than a tuple, so this is the second
    half of the child definition rather than a consequence of the first. A
    census that stopped at the table would report a dispatch table as one
    childless node, which is a flavour's whole anatomy made invisible.
    """
    key, value = IrStr("k"), IrLiteral("v")
    table = IrMap(IrTuple(key, value))
    assert field_children(table) == (key, value)
    assert len(census(table)) == 3


def test_a_type_keyed_tables_children_are_its_bodies() -> None:
    """An ``IrTypeMap`` keys by CLASS, so only its bodies are nodes."""
    body = IrLiteral("v")
    table = IrTypeMap(IrAction(IrLiteral, body))
    assert field_children(table) == (body,)


def test_field_children_is_wider_than_the_dispatch_children(json_ast: IrAst) -> None:
    """Every dispatched child is a field child; a real AST has more besides.

    ``IrRule`` excludes its own name from ``_child_attrs`` and the name IS a
    node — an identity walk that used the dispatch definition would not count
    it, which is the undercount this module exists to avoid.
    """
    rule = json_ast.rules[0]
    dispatched = {id(child) for child in rule.children()}
    fields = {id(child) for child in field_children(rule)}
    assert dispatched < fields
    assert id(rule.name) in fields


# ── unique nodes and share counts ─────────────────────────────────────


def test_a_lone_leaf_censuses_as_one_node() -> None:
    """The root is always the first entry, reached once."""
    entries = census(IrLiteral("a"))
    assert len(entries) == 1
    assert entries[0].node == IrLiteral("a")
    assert entries[0].reached == 1


def test_one_object_in_two_places_is_one_node_reached_twice() -> None:
    """Sharing is by identity: one object, one entry, two arrivals."""
    shared = IrLiteral("a")
    entries = census(IrTuple(shared, shared))
    assert len(entries) == 2
    assert entries[1].node is shared
    assert entries[1].reached == 2


def test_equal_but_distinct_nodes_are_two_entries() -> None:
    """Equal values are different occurrences — the walk counts identity."""
    entries = census(IrTuple(IrLiteral("a"), IrLiteral("a")))
    assert len(entries) == 3
    assert all(entry.reached == 1 for entry in entries)


def test_absence_is_a_node_like_any_other() -> None:
    """``IrNone`` is a value with a place in the graph, never a hole."""
    entries = census(IrTuple(IrNone))
    assert [entry.node for entry in entries][1] is IrNone


def test_shared_selects_the_re_reached_nodes(json_ast: IrAst) -> None:
    """The shared sub-census is exactly the entries reached more than once."""
    entries = census(json_ast)
    assert [entry for entry in entries if entry.reached > 1] == list(entries.shared())


def test_arrivals_are_one_per_edge_plus_the_root(json_ast: IrAst) -> None:
    """Conservation: every arrival is an edge, except the walk's own entry.

    The census is checked against the definition it names rather than against
    a second traversal, which would only agree with itself.
    """
    entries = census(json_ast)
    edges = sum(len(field_children(entry.node)) for entry in entries)
    assert sum(entry.reached for entry in entries) == edges + 1


def test_every_entry_is_a_distinct_object(json_ast: IrAst) -> None:
    """One entry per object — the census never lists a node twice."""
    entries = census(json_ast)
    assert len({id(entry.node) for entry in entries}) == len(entries)


def test_the_order_is_the_pre_order_walk() -> None:
    """Root first, then each subtree in field order — depth before breadth."""
    first, second, third = IrLiteral("a"), IrLiteral("b"), IrLiteral("c")
    inner = IrTuple(first, second)
    root = IrTuple(inner, third)
    entries = census(root)
    assert [entry.node for entry in entries] == [root, inner, first, second, third]


def test_the_root_is_always_the_first_entry(json_ast: IrAst) -> None:
    """The walk enters at the root, so the census opens with it."""
    assert census(json_ast)[0].node is json_ast


def test_a_deep_chain_does_not_exhaust_the_stack() -> None:
    """Iterative by construction — depth is a heap cost, not a frame cost."""
    node: IrSelf = IrLiteral("a")
    for _ in range(10_000):
        node = IrTuple(node)
    assert len(census(node)) == 10_001


# ── the refusal boundary ──────────────────────────────────────────────


def test_a_lambda_is_on_the_refusal_boundary() -> None:
    """The one node whose payload is a callable — no text can name it."""
    body = IrLambda(len)
    entries = census(IrTuple(body, IrLiteral("a")))
    assert [entry.node for entry in entries.refusals()] == [body]


def test_a_class_is_not_a_refusal() -> None:
    """A class has a name, and the notation spells names."""
    assert not unspellable(IrTuple(IrLiteral, IrLiteral("a")))


def test_a_parsed_grammar_has_no_refusals(json_ast: IrAst) -> None:
    """A grammar AST is spellable end to end — the boundary is elsewhere."""
    assert len(census(json_ast).refusals()) == 0


def test_a_compiled_folds_class_constructors_are_the_refusal_boundary() -> None:
    """Where the boundary really is, on a real artefact.

    A compiled grammar's fold files one ``IrLambda(<class>)`` per built rule,
    and those tables are reachable only through the map half of the child
    definition — under the field-tuple half alone this whole census was ONE
    node and the boundary read as an empty set.
    """
    bodies = compile_from_path(GROUND_TRUTH / "json.gbnf").fold.bodies
    refusals = census(bodies).refusals()
    assert len(refusals) > 10
    assert all(isinstance(entry.node, IrLambda) for entry in refusals)


def test_a_flavours_reducer_censuses_its_whole_anatomy() -> None:
    """The reducer opens up: the tables, their keys, and every body.

    It carries no refusals of its own — a flavour's bodies are pure IR
    algebra, which is the repo's own rule and not an accident of this walk —
    so the anatomy is the fact being gated here, not the boundary.
    """
    entries = census(GBNF_FLAVOUR.reducer)
    assert len(entries) > 100
    assert len(entries.shared()) > 1
    assert len(entries.refusals()) == 0


def test_a_census_is_a_sequence_of_records(json_ast: IrAst) -> None:
    """The product IS its entries — read with plain Python, no accessors."""
    entries = census(json_ast)
    node, reached, refused = entries[0]
    assert node is json_ast
    assert reached == 1
    assert refused is False
