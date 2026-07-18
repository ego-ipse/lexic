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

The ``lexic.compile`` package builds the codegen grammar via
:func:`build_codegen_grammar` and hands it to both synthesis and the instance
fold.
"""

from __future__ import annotations

from lexic.compile.pipeline.binding import classify_rule, has_ruleref, unit_ref_arm
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import Field, IrLambda, IrNode, IrNone, IrNoneType, IrSelf, IrSeq
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk import IrBottomUp, IrDispatch


def _reserve_helper_name(parent_name: str, taken: set[str]) -> str:
    """Return ``<parent_name>-item[N]``, the lowest ``N`` not already taken."""
    base = f"{parent_name}-item"
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def _extract_group(
    _d: object, group: IrAlternation, _nc: object
) -> IrAlternation | IrNoneType:
    """Return the group body if it contains a ruleref, else :data:`IrNone`."""
    return group if has_ruleref(group) else IrNone


_EXTRACT_BODY: IrDispatch = IrDispatch(
    actions=IrTypeMap(IrAction(IrAlternation, IrLambda(_extract_group))),
    # Non-IrAlternation atoms never hoist: IrNone is self-evaluating, so it
    # serves as the "extract nothing" body directly — no procedural wrapper.
    default=IrNone,
)


def _hoist_item(d: IrNode, item: IrItem, _nc: object) -> IrItem:
    """Hoist a quantified ref-bearing group atom to a helper rule.

    The bottom-up driver has already rewritten anything nested inside the
    atom, so the body only decides this item's fate.

    :param d: The :class:`_HoistTransformer` driving the walk.
    :param item: The :class:`IrItem` being rewritten (children final).
    :param _nc: Pre-dispatched children (unused).
    :returns: The rewritten :class:`IrItem`.
    """
    if not isinstance(d, _HoistTransformer):
        raise TypeError(f"Expected _HoistTransformer, got {type(d).__name__}")
    if item.quantifier == IrQuantifier(1, 1):
        return item
    extracted = _EXTRACT_BODY.apply(item.atom)
    if extracted is IrNone:
        return item
    name = _reserve_helper_name(d.parent_name, d.name_set)
    d.name_set.add(name)
    d.helpers.append(IrRule(name=name, body=extracted))
    return IrItem(atom=IrRuleRef(name), quantifier=item.quantifier)


class _HoistTransformer[Iri: IrSelf, Ir_co: IrNode](IrBottomUp[Iri, Ir_co]):
    """Hoist quantified groups-with-rulerefs into synthetic helper rules.

    Pure-literal groups (no :class:`IrRuleRef` anywhere) are left intact
    regardless of their quantifier so codegen can treat them as regex patterns.

    :ivar parent_name: Enclosing rule name; used to derive helper names.
    :ivar name_set: Mutable set of taken rule names, shared across per-rule
        dispatchers so allocation stays globally unique.
    :ivar helpers: Mutable list of emitted helper rules — per-rule fresh.
    """

    parent_name: str = ""
    name_set: set[str] = Field(default_factory=set)
    helpers: list[IrRule] = Field(default_factory=list)
    actions: IrTypeMap = IrTypeMap(IrAction(IrItem, IrLambda(_hoist_item)))


def hoist_groups(ast: IrAst) -> IrAst:
    """Hoist quantified ref-bearing groups into named helper rules.

    Pure-literal groups keep their quantifier inline (they stay regex
    patterns); helper rules land after the original rules. ``name_set`` is
    shared across the per-rule dispatchers so helper names stay globally
    unique; each rule's ``helpers`` list is fresh.

    :param ast: The canonical grammar.
    :returns: The grammar with helper rules appended.
    """
    name_set: set[str] = {str(r.name) for r in ast.rules}
    helpers: list[IrRule] = []
    rules: list[IrRule] = []
    for rule in ast.rules:
        transformer = _HoistTransformer(parent_name=rule.name, name_set=name_set)
        new_body = transformer.apply(rule.body)
        helpers.extend(transformer.helpers)
        rules.append(IrRule(rule.name, new_body, rule.semantic))
    return IrAst(IrSeq(*rules, *helpers), ast.start)


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
