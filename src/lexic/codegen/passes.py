"""Grammar→grammar codegen passes — hoist groups, hoist arms, relax noise.

The canonical AST becomes THE codegen grammar through three
language-preserving-for-instances rewrites::

    codegen_grammar = relax_non_semantic(hoist_arms(hoist_groups(ast)))

- :func:`hoist_groups` — quantified ref-bearing groups become named helper
  rules (``<rule>-item``), so every repeated model field is a rule of its own.
- :func:`hoist_arms` — every non-empty alternation arm that is not already a
  single unit ruleref hoists to a ``<rule>-arm<N>`` sequence rule, restoring
  the single-arm premise the positional fold rests on. Empty arms stay in
  place (zero-kid matches discriminate themselves).
- :func:`relax_non_semantic` — refs to ``semantic=False`` rules get ``min=0``.

``compile.py`` orchestrates these (Task 5); until then the passes are consumed
by the binding view's tests and the derive-parity scaffold.
"""

from __future__ import annotations

from lexic.codegen.binding import classify_rule, unit_ref_arm
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNoneType, IrSeq
from lexic.ir.derive import hoist_helpers
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)


def hoist_groups(ast: IrAst) -> IrAst:
    """Hoist quantified ref-bearing groups into named helper rules.

    Pure-literal groups keep their quantifier inline (they stay regex
    patterns); helper rules land after the original rules.

    The rewrite itself is :func:`~lexic.ir.derive.hoist_helpers` — its
    implementation moves here when ``ir/derive.py`` dies in Task 6.

    :param ast: The canonical grammar.
    :returns: The grammar with helper rules appended.
    """
    hoisted, helpers = hoist_helpers(ast)
    return IrAst(IrSeq(*hoisted.rules, *helpers), hoisted.start)


def _hoist_rule_arms(rule: IrRule, taken: set[str]) -> list[IrRule]:
    """Hoist one alternation rule's non-ref arms; returns rule + arm rules.

    :param rule: An ``alternation``-kind rule.
    :param taken: All rule names in the grammar (collision guard).
    :raises UnsupportedConstructError: If a synthesized ``-arm<N>`` name is
        already a rule.
    """
    arms: list[IrSequence] = []
    hoisted: list[IrRule] = []
    arm_index = 0
    for arm in rule.body:
        if not arm:
            arms.append(arm)  # empty arm stays — zero kids discriminate it
            continue
        arm_index += 1
        if not isinstance(unit_ref_arm(arm), IrNoneType):
            arms.append(arm)
            continue
        name = f"{rule.name}-arm{arm_index}"
        if name in taken:
            raise UnsupportedConstructError(
                f"passes: arm rule {name!r} collides with an existing rule"
            )
        taken.add(name)
        hoisted.append(IrRule(name, IrAlternation(arm)))
        arms.append(IrSequence(IrItem(IrRuleRef(name))))
    rebuilt = IrRule(rule.name, IrAlternation(*arms), rule.semantic)
    return [rebuilt, *hoisted]


def hoist_arms(ast: IrAst) -> IrAst:
    """Hoist every multi-item / non-ref arm of alternation rules.

    After this pass every non-empty arm of an ``alternation``-kind rule is a
    single unit ruleref; hoisted ``<rule>-arm<N>`` rules follow their
    alternation immediately (``N`` counts non-empty arms from 1).

    :param ast: The grammar (typically post :func:`hoist_groups`).
    :returns: The grammar with arm rules inserted.
    :raises UnsupportedConstructError: On an arm-name collision.
    """
    taken = {str(rule.name) for rule in ast.rules}
    out: list[IrRule] = []
    for rule in ast.rules:
        if classify_rule(rule) == "alternation":
            out.extend(_hoist_rule_arms(rule, taken))
        else:
            out.append(rule)
    return IrAst(IrSeq(*out), ast.start)


def _relaxed_item(item: IrItem, non_semantic: frozenset[str]) -> IrItem:
    """``min=0`` on a ref to a structural-noise rule; other items unchanged."""
    if (
        isinstance(item.atom, IrRuleRef)
        and item.atom in non_semantic
        and item.quantifier.lo > 0
    ):
        return IrItem(item.atom, IrQuantifier(0, item.quantifier.hi))
    return item


def relax_non_semantic(ast: IrAst) -> IrAst:
    """Relax the quantifier of every top-level ref to a non-semantic rule.

    Only arm-level items relax (refs inside inline groups keep their bounds),
    matching the spec-level relaxation the old derive pipeline applied.

    :param ast: The grammar carrying ``semantic=False`` flags on noise rules.
    :returns: The relaxed grammar; unchanged when no rule is flagged.
    """
    targets = ast.non_semantic
    if not targets:
        return ast
    rules = [
        IrRule(
            rule.name,
            IrAlternation(
                *(
                    IrSequence(*(_relaxed_item(item, targets) for item in arm))
                    for arm in rule.body
                )
            ),
            rule.semantic,
        )
        for rule in ast.rules
    ]
    return IrAst(IrSeq(*rules), ast.start)


def build_codegen_grammar(ast: IrAst) -> IrAst:
    """THE codegen grammar: groups hoisted, arms hoisted, noise refs relaxed.

    :param ast: The canonical grammar with semantic flags bound.
    :returns: The grammar codegen, emission and the instance fold all share.
    """
    return relax_non_semantic(hoist_arms(hoist_groups(ast)))
