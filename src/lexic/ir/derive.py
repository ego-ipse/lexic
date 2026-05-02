"""derive_specs — IR AST → list[RuleSpec] (the codegen view).

Pure, flavour-agnostic structural decomposition. No flavour parameter:
RuleSpec is a structural projection of the IR AST.

This module is built up across tasks 5-8. Task 5 adds classify_kind;
tasks 6-8 add compute_parents, hoist_helpers, and derive_specs itself.
"""

from __future__ import annotations

from typing import Literal

from lexic.ir.nodes import IrAlternation, IrNode, IrRule, IrRuleRef, IrSequence
from lexic.ir.walk import IrVisitor
from lexic.utils.names import to_pascal

# ── classify_kind ─────────────────────────────────────────────────────


def _has_ruleref(node: IrNode) -> bool:
    """Return True iff the subtree rooted at `node` contains any IrRuleRef."""
    finder = _RuleRefFinder()
    finder.visit(node)
    return finder.found


class _RuleRefFinder(IrVisitor):
    """Visitor that sets `found` when any IrRuleRef is encountered."""

    def __init__(self) -> None:
        self.found = False

    def visit(self, node: IrNode) -> None:
        if not self.found:
            super().visit(node)

    def visit_IrRuleRef(self, _node: IrRuleRef) -> None:  # pylint: disable=invalid-name
        """Set found flag — presence of any IrRuleRef is sufficient."""
        self.found = True


def _non_empty_arms(body: IrAlternation) -> list[IrSequence]:
    """Return the non-empty arms of an alternation."""
    return [a for a in body.arms if a.items]


def classify_kind(rule: IrRule) -> Literal["sequence", "alternation", "value_str"]:
    """Classify a rule's body into one of the three IR kinds.

    Rules:
      - value_str: no IrRuleRef anywhere in the body (entire subtree).
      - alternation: multiple non-empty arms with rulerefs.
      - sequence: single non-empty arm with rulerefs.
    """
    if not _has_ruleref(rule.body):
        return "value_str"
    arms = _non_empty_arms(rule.body)
    if len(arms) > 1:
        return "alternation"
    return "sequence"


def _single_unquantified_ruleref(arm: IrSequence) -> str | None:
    """If arm is a single IrItem(IrRuleRef, Quantifier(1,1)), return the ref name."""
    if len(arm.items) != 1:
        return None
    item = arm.items[0]
    if not isinstance(item.atom, IrRuleRef):
        return None
    if item.quantifier.min != 1 or item.quantifier.max != 1:
        return None
    return item.atom.name


def compute_parents(rules: list[IrRule]) -> dict[str, str]:
    """For each rule appearing as a single-unquantified-ref arm in some
    alternation, set its parent class to that alternation's class name.
    """
    parent_of: dict[str, str] = {}
    for rule in rules:
        if classify_kind(rule) != "alternation":
            continue
        parent_cls = to_pascal(rule.name)
        for arm in _non_empty_arms(rule.body):
            ref = _single_unquantified_ruleref(arm)
            if ref is not None:
                parent_of[ref] = parent_cls
    return parent_of
