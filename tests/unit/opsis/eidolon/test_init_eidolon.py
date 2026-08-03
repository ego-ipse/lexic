"""Eidolon contract — layout centring/roots, and Topology's depths and refs."""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from opsis.eidolon.layout import layout
from opsis.eidolon.topology import Topology


def test_layout_centres_a_parent_over_its_children() -> None:
    """A parent's column is the mean of its children's columns."""
    parents = {"a": "", "b": "a", "c": "a"}
    idents = ["a", "b", "c"]
    place = layout(parents, idents)
    ax, _ = place["a"]
    bx, _ = place["b"]
    cx, _ = place["c"]
    assert ax == (bx + cx) // 2


def test_layout_gives_roots_distinct_columns() -> None:
    """Readings nobody reads are roots, spread left to right."""
    parents: dict[str, str] = {"a": "", "b": ""}
    idents = ["a", "b"]
    place = layout(parents, idents)
    assert place["a"][0] != place["b"][0]


def test_layout_treats_an_absent_parent_as_a_root() -> None:
    """Naming a parent that is not among the idents still makes a root."""
    parents = {"a": "ghost"}
    idents = ["a"]
    place = layout(parents, idents)
    assert "a" in place


def test_topology_depth_zero_at_the_start_rule() -> None:
    """The start rule sits at depth zero."""
    ast = parse_grammar('root ::= a b\na ::= "x"\nb ::= "y"\n', GBNF_FLAVOUR)
    topology = Topology(ast)
    assert topology.levels[topology.start] == 0


def test_topology_depth_minus_one_for_an_unreachable_rule() -> None:
    """A rule nothing references from the start is unreachable."""
    ast = parse_grammar('root ::= "x"\norphan ::= "y"\n', GBNF_FLAVOUR)
    topology = Topology(ast)
    assert topology.levels["orphan"] == -1


def test_topology_out_names_only_rules_the_grammar_defines() -> None:
    """A rule's outgoing refs never name anything the grammar does not define."""
    ast = parse_grammar('root ::= a\na ::= "x"\n', GBNF_FLAVOUR)
    topology = Topology(ast)
    defined = set(topology.names)
    for refs in topology.out.values():
        assert set(refs) <= defined
    assert topology.out["root"] == ["a"]
