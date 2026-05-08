"""topo_sort: orders specs so parent classes come before subclasses; start rule first."""

from __future__ import annotations

from collections.abc import Callable

from lexic.ir import RuleSpec
from lexic.ir.topo import topo_sort


def _spec(name: str, parent: str = "GrammarModel") -> RuleSpec:
    """Helper to create a RuleSpec with the given name and parent."""
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name=parent,
        kind="sequence",
        items=[],
        field_map={},
    )


def _is_start(name: str) -> Callable[[RuleSpec], bool]:
    """Helper to create a predicate that matches a RuleSpec with the given name."""

    def predicate(spec: RuleSpec) -> bool:
        return spec.rule_name == name

    return predicate


def test_topo_sort_puts_start_rule_first():
    """The start rule should be first in the output list."""
    a, b, root = _spec("a"), _spec("b"), _spec("root")
    out = topo_sort([a, b, root], is_start_rule=_is_start("root"))
    assert out[0].rule_name == "root"


def test_topo_sort_orders_parents_before_subclasses():
    """Parent classes should come before their subclasses in the output list."""
    parent = _spec("term")
    child = _spec("expr", parent="Term")
    root = _spec("root")

    out = topo_sort([child, parent, root], is_start_rule=_is_start("root"))
    rule_names = [s.rule_name for s in out]
    assert rule_names.index("term") < rule_names.index("expr")
    assert rule_names[0] == "root"


def test_topo_sort_no_start_rule_falls_back_to_input_order():
    """If no start rule is found, the output order should be the same as the input order."""
    a, b = _spec("a"), _spec("b")
    out = topo_sort([a, b], is_start_rule=_is_start("nonexistent"))
    assert [s.rule_name for s in out] == ["a", "b"]
