"""classify_rule: generic algorithm; takes a RuleClassifier protocol impl."""

from __future__ import annotations

from dataclasses import dataclass

from lexic.ir.classify import classify_rule


# Fake AST node + classifier for testing. No GBNF imports.
@dataclass(frozen=True)
class FakeNode:
    """A fake AST node with just the fields needed for testing classify_rule."""

    name: str
    kind: str  # "sequence" | "alternation" | "value_str"


class FakeClassifier:
    """A fake RuleClassifier that uses the kind field of FakeNode."""

    def rule_name(self, rule):
        """Return the rule name, which is just the node's name."""
        return rule.name

    def is_start_rule(self, rule):
        """The start rule is the one named "start"."""
        return rule.name == "start"

    def kind(self, rule):
        """Return the kind of the rule, which is just the node's kind."""
        return rule.kind

    def alternation_arm_nodes(self, rule):
        """Return the arms of an alternation, which we don't need for these tests."""
        assert isinstance(rule, object)
        return []

    def sequence_body(self, rule):
        """Return the body of a sequence rule."""
        return rule

    def value_str_body(self, rule):
        """Return the body of a value_str rule."""
        return rule

    def single_ruleref(self, arm):
        """Return the single rule reference for an alternation arm."""
        assert isinstance(arm, object)


def test_classify_returns_kind_from_classifier():
    """classify_rule should return the kind as determined by the classifier."""
    rule = FakeNode(name="r", kind="sequence")
    assert classify_rule(rule, FakeClassifier()) == "sequence"


def test_classify_value_str():
    """classify_rule should return "value_str" for a value_str rule."""
    rule = FakeNode(name="lit", kind="value_str")
    assert classify_rule(rule, FakeClassifier()) == "value_str"


def test_classify_alternation():
    """classify_rule should return "alternation" for an alternation rule."""
    rule = FakeNode(name="alt", kind="alternation")
    assert classify_rule(rule, FakeClassifier()) == "alternation"
