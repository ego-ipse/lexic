"""derive_specs — IR AST → list[RuleSpec] (the codegen view).

Pure, flavour-agnostic structural decomposition. No flavour parameter:
RuleSpec is a structural projection of the IR AST.

This module is built up across tasks 5-8. Task 5 adds classify_kind;
tasks 6-8 add compute_parents, hoist_helpers, and derive_specs itself.
"""

from __future__ import annotations

from typing import Literal

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrGroup,
    IrItem,
    IrNode,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.walk import IrTransformer, IrVisitor
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


# ── hoist_helpers ─────────────────────────────────────────────────────


def _reserve(parent_name: str, taken: set[str]) -> str:
    """Return '<parent_name>-item[N]', the lowest N not already in `taken`."""
    base = f"{parent_name}-item"
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


class _HoistTransformer(IrTransformer):
    """Rewrites quantified IrGroup nodes containing IrRuleRefs into synthetic rules.

    For each IrItem whose atom is an IrGroup with a non-trivial quantifier
    and whose body contains at least one IrRuleRef, the group is replaced by
    an IrItem(IrRuleRef(helper_name), quantifier). The group body becomes the
    body of a new IrRule appended to `self.helpers`.

    Pure-literal groups (no IrRuleRef anywhere) are left intact regardless
    of their quantifier so that codegen can treat them as regex patterns.
    """

    def __init__(self, parent_name: str, name_set: set[str]) -> None:
        self._parent_name = parent_name
        self._name_set = name_set
        self.helpers: list[IrRule] = []

    def visit_IrItem(self, node: IrItem) -> IrItem:  # pylint: disable=invalid-name
        """Recurse into the atom first so nested groups are processed bottom-up."""
        new_atom = self.visit(node.atom)
        if not isinstance(new_atom, IrGroup):
            if new_atom is node.atom:
                return node
            return IrItem(atom=new_atom, quantifier=node.quantifier)

        is_quantified = node.quantifier != Quantifier(1, 1)
        if is_quantified and _has_ruleref(new_atom.body):
            helper_name = _reserve(self._parent_name, self._name_set)
            self._name_set.add(helper_name)
            self.helpers.append(IrRule(name=helper_name, body=new_atom.body))
            return IrItem(atom=IrRuleRef(name=helper_name), quantifier=node.quantifier)
        return IrItem(atom=new_atom, quantifier=node.quantifier)


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    """Rewrite groups-with-rulerefs-and-non-trivial-quantifiers into synthetic rules.

    A group `(g)` with quantifier q is hoisted iff:
      - q != Quantifier(1, 1), AND
      - g contains any IrRuleRef.

    Pure literal-only groups are NEVER hoisted (they remain inline for
    codegen to treat as regex patterns).
    """
    name_set: set[str] = {r.name for r in ast.rules}
    helpers: list[IrRule] = []
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        t = _HoistTransformer(parent_name=rule.name, name_set=name_set)
        new_body = t.visit(rule.body)
        helpers.extend(t.helpers)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), helpers
