"""IRBuilder: generic orchestrator parameterised by RuleClassifier + SequenceConverter."""

from __future__ import annotations

from dataclasses import dataclass

from lexic.ir import (
    Atom,
    LiteralAtom,
    RuleRefAtom,
)
from lexic.ir.builder import IRBuilder


@dataclass(frozen=True)
class FakeNode:
    """A fake AST node with just the fields needed for testing IRBuilder."""

    name: str
    kind: str
    items: list[Atom]
    arms: list | None = None  # for alternation
    is_start: bool = False


class FakeClassifier:
    """A RuleClassifier that just reads the relevant info from the node."""

    def rule_name(self, rule):
        """The rule name is just the node's name."""

        return rule.name

    def is_start_rule(self, rule):
        """The start rule is just the node's is_start field."""
        return rule.is_start

    def kind(self, rule):
        """The rule kind is just the node's kind."""
        return rule.kind

    def alternation_arm_nodes(self, rule):
        """The alternation arms are just the node's arms."""
        return rule.arms or []

    def sequence_body(self, rule):
        """The sequence body is just the node itself."""
        return rule

    def value_str_body(self, rule):
        """The value_str body is just the node itself."""
        return rule

    def single_ruleref(self, arm):
        """If the arm consists of a single RuleRefAtom, return its rule name; otherwise None."""
        if len(arm.items) == 1 and isinstance(arm.items[0], RuleRefAtom):
            return arm.items[0].rule_name
        return None


class FakeConverter:
    """A SequenceConverter that just returns the items of the body as atoms."""

    def value_str_atoms(self, body):
        """The value_str atoms are just the body's items."""
        return list(body.items)

    def sequence_atoms(self, body, parent_class_name, helpers):
        """The sequence atoms are just the body's items."""
        assert isinstance(parent_class_name, str)
        assert helpers.all_specs() is not None
        return list(body.items)


def test_builder_value_str_rule_produces_one_value_str_spec():
    """A value_str rule should produce exactly one value_str spec."""
    rule = FakeNode(
        name="num", kind="value_str", items=[LiteralAtom(value="0")], is_start=True
    )
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    specs = builder.build([rule])
    assert len(specs) == 1
    assert specs[0].rule_name == "num"
    assert specs[0].kind == "value_str"


def test_builder_sets_min_zero_on_trivia_refs():
    """Trivia rules should be treated as optional and non-semantic."""
    rule = FakeNode(
        name="root",
        kind="sequence",
        items=[RuleRefAtom("ws", 1, 1), RuleRefAtom("expr", 1, 1)],
        is_start=True,
    )
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    specs = builder.build([rule])
    ws_atom = specs[0].items[0]
    assert isinstance(ws_atom, RuleRefAtom)
    assert ws_atom.min == 0  # trivia rule → optional


def test_builder_populates_non_semantic_fields_for_trivia_refs():
    """Fields corresponding to trivia rules should be marked non-semantic."""
    rule = FakeNode(
        name="root",
        kind="sequence",
        items=[RuleRefAtom("ws", 1, 1), RuleRefAtom("expr", 1, 1)],
        is_start=True,
    )
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    spec = builder.build([rule])[0]
    # The "ws" field maps to the ws atom; that field must be in non_semantic_fields.
    ws_field = next(
        name
        for name, idx in spec.field_map.items()
        if isinstance(item := spec.items[idx], RuleRefAtom) and item.rule_name == "ws"
    )
    assert ws_field in spec.non_semantic_fields


def test_builder_custom_trivia_rules_parameter():
    """Custom trivia rules should be treated as optional and non-semantic."""
    rule = FakeNode(
        name="root",
        kind="sequence",
        items=[RuleRefAtom("ignore", 1, 1)],
        is_start=True,
    )
    builder = IRBuilder(
        FakeClassifier(), FakeConverter(), trivia_rules=frozenset({"ignore"})
    )
    spec = builder.build([rule])[0]
    first = spec.items[0]
    assert isinstance(first, RuleRefAtom)
    assert first.min == 0


def test_builder_topo_sorts_with_start_rule_first():
    """The start rule should be first in the output list, even if it comes later in the input."""
    other = FakeNode(name="other", kind="sequence", items=[], is_start=False)
    root = FakeNode(name="root", kind="sequence", items=[], is_start=True)
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    specs = builder.build([other, root])
    assert specs[0].rule_name == "root"
