"""Type-aware routes and immutable replacement inside grammar models."""

from __future__ import annotations

from typing import Any, NamedTuple, cast

from lexic.exceptions import LexicError
from lexic.ir import IrAst, IrItem, IrRule, IrRuleRef
from lexic.model import GrammarModel
from lexic.parsing.fold import ModelFold, RuleFold
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.discovery.shapes import unbounded


class RegionPlan(NamedTuple):
    """The model-bearing shape of one bracketed region rule."""

    root: IrAst
    outer_type: type[GrammarModel]
    items_type: type[GrammarModel]
    tail_type: type[GrammarModel]
    outer_begin: int | None
    outer_items: int
    outer_end: int | None
    items_head: int
    items_rest: int
    tail_head: int


class RegionWork(NamedTuple):
    """One chosen region, its balanced source pieces, and stitch plan."""

    region: Region
    parts: list[str]
    cuts: list[int]
    plan: RegionPlan


def model_type(config: RuleFold | None) -> type[GrammarModel] | None:
    """The generated model class a fold config constructs, when explicit."""
    ctor = config.ctor if config is not None else None
    if isinstance(ctor, type) and issubclass(ctor, GrammarModel):
        return ctor
    return None


def field_slot(config: RuleFold, item: int) -> int | None:
    """The item-ordered model-child slot bound from grammar item ``item``."""
    fields = sorted(config.fields, key=lambda field: field.item)
    return next((slot for slot, field in enumerate(fields) if field.item == item), None)


def _single_arm(rule: IrRule) -> tuple[IrItem, ...] | None:
    """The items of a rule's sole arm, when it has exactly one."""
    return tuple(rule.body[0]) if len(rule.body) == 1 else None


def _ref_at(items: tuple[IrItem, ...], at: int) -> str | None:
    """The rule reference at one arm position, ignoring its quantifier."""
    atom = items[at].atom
    return str(atom) if isinstance(atom, IrRuleRef) else None


def _candidate(
    rules: dict[str, IrRule], outer_arm: tuple[IrItem, ...], at: int
) -> tuple[str, str] | None:
    """The items/tail recurrence rooted at one outer-arm position."""
    items_name = _ref_at(outer_arm, at)
    items_rule = rules.get(items_name or "")
    items_arm = _single_arm(items_rule) if items_rule is not None else None
    if items_name is None or items_arm is None or len(items_arm) != 2:
        return None
    head, tail_name = _ref_at(items_arm, 0), _ref_at(items_arm, 1)
    tail_rule = rules.get(tail_name or "")
    tail_arm = _single_arm(tail_rule) if tail_rule is not None else None
    valid_tail = (
        tail_arm is not None and len(tail_arm) == 2 and _ref_at(tail_arm, 1) == head
    )
    if head is None or tail_name is None or not unbounded(items_arm[1]):
        return None
    return (items_name, tail_name) if valid_tail else None


class _PlanInput(NamedTuple):
    """Inputs already derived before model-fold binding begins."""

    root: IrAst
    fold: ModelFold
    rule_name: str
    outer_arm: tuple[IrItem, ...]
    candidate: tuple[int, str, str]


def _configured_plan(source: _PlanInput) -> RegionPlan | None:
    """Bind a derived recurrence to exact generated model slots/classes."""
    items_at, items_name, tail_name = source.candidate
    configs = (
        source.fold.config.get(source.rule_name),
        source.fold.config.get(items_name),
        source.fold.config.get(tail_name),
    )
    if any(config is None for config in configs):
        return None
    outer_cfg, items_cfg, tail_cfg = cast(tuple[RuleFold, RuleFold, RuleFold], configs)
    slots = (
        field_slot(outer_cfg, items_at),
        field_slot(items_cfg, 0),
        field_slot(items_cfg, 1),
        field_slot(tail_cfg, 1),
    )
    kinds = (model_type(outer_cfg), model_type(items_cfg), model_type(tail_cfg))
    if any(slot is None for slot in slots) or any(kind is None for kind in kinds):
        return None
    begin = end = None
    if len(source.outer_arm) == 3 and items_at == 1:
        if (
            _ref_at(source.outer_arm, 0) is not None
            and _ref_at(source.outer_arm, 2) is not None
        ):
            begin, end = field_slot(outer_cfg, 0), field_slot(outer_cfg, 2)
    return RegionPlan(
        root=source.root,
        outer_type=cast(type[GrammarModel], kinds[0]),
        items_type=cast(type[GrammarModel], kinds[1]),
        tail_type=cast(type[GrammarModel], kinds[2]),
        outer_begin=begin,
        outer_items=cast(int, slots[0]),
        outer_end=end,
        items_head=cast(int, slots[1]),
        items_rest=cast(int, slots[2]),
        tail_head=cast(int, slots[3]),
    )


def derive_plan(
    grammar: IrAst, fold: ModelFold, rule_name: str, roots: dict[str, IrAst]
) -> RegionPlan | None:
    """Derive the unique repeated-items child of one bracket rule.

    Brackets and whitespace may be referenced wrapper rules or inline grammar
    items. Only the items/tail recurrence is essential. Exact three-reference
    wrappers additionally expose their boundary fields for source restoration.
    """
    rules = {str(rule.name): rule for rule in grammar.rules}
    outer = rules.get(rule_name)
    outer_arm = _single_arm(outer) if outer is not None else None
    if outer_arm is None:
        return None
    candidates = [
        (at, *candidate)
        for at in range(len(outer_arm))
        if (candidate := _candidate(rules, outer_arm, at)) is not None
    ]
    if len(candidates) != 1:
        return None
    root = roots.setdefault(rule_name, IrAst(grammar.rules, rule_name))
    return _configured_plan(_PlanInput(root, fold, rule_name, outer_arm, candidates[0]))


def region_items(model: GrammarModel, plan: RegionPlan) -> GrammarModel | None:
    """The region's items child, guarded by exact generated class."""
    if model.__class__ is not plan.outer_type:
        return None
    children = model.children()
    if plan.outer_items >= len(children):
        return None
    items = children[plan.outer_items]
    return cast(GrammarModel, items) if items.__class__ is plan.items_type else None


def head_rest(
    items: GrammarModel, plan: RegionPlan
) -> tuple[GrammarModel, tuple[GrammarModel, ...]] | None:
    """One items node's head and plain-tuple repeated tails."""
    children = items.children()
    if max(plan.items_head, plan.items_rest) >= len(children):
        return None
    head, rest = children[plan.items_head], children[plan.items_rest]
    if not isinstance(head, GrammarModel) or rest.__class__ is not tuple:
        return None
    tails = cast(tuple[object, ...], rest)
    if any(tail.__class__ is not plan.tail_type for tail in tails):
        return None
    return head, cast(tuple[GrammarModel, ...], tails)


type ModelStep = tuple[int, int | None]
"""One model-child slot and, for a repeated field, its tuple index."""


def sole_route(
    root: GrammarModel, needle: GrammarModel
) -> tuple[ModelStep, ...] | None:
    """Find the unique exact-class/equal-value route below ``root``.

    :param root: The shell model to search.
    :param needle: A region's distinct items-node stand-in.
    :returns: Its non-root route, or ``None`` on absence or collision.
    """
    found: tuple[ModelStep, ...] | None = None
    stack: list[tuple[GrammarModel, tuple[ModelStep, ...]]] = [(root, ())]
    while stack:
        node, route = stack.pop()
        if node.__class__ is needle.__class__ and node == needle:
            if found is not None:
                return None
            found = route
        for slot, child in enumerate(node.children()):
            if isinstance(child, GrammarModel):
                stack.append((child, (*route, (slot, None))))
            elif child.__class__ is tuple:
                parts = cast(tuple[object, ...], child)
                stack.extend(
                    (part, (*route, (slot, at)))
                    for at, part in enumerate(parts)
                    if isinstance(part, GrammarModel)
                )
    return found if found else None


def _nested(
    child: object, route: tuple[ModelStep, ...], value: GrammarModel
) -> GrammarModel | None:
    """Replacement at or below one already selected model child."""
    if not isinstance(child, GrammarModel):
        return None
    return value if len(route) == 1 else splice(child, route[1:], value)


def splice(
    root: GrammarModel, route: tuple[ModelStep, ...], value: GrammarModel
) -> GrammarModel | None:
    """Replace the model at ``route``, immutably rebuilding its ancestors.

    :param root: The current shell model.
    :param route: A route returned by :func:`sole_route`.
    :param value: The replacement items node.
    :returns: The rebuilt model, or ``None`` on a shape surprise.
    """
    if not route:
        return None
    slot, repeated = route[0]
    children = cast(list[Any], list(root.children()))
    if slot >= len(children):
        return None
    child = children[slot]
    if repeated is None:
        replacement = _nested(child, route, value)
    else:
        if child.__class__ is not tuple or repeated >= len(child):
            return None
        parts = list(child)
        replacement = _nested(parts[repeated], route, value)
        if replacement is not None:
            parts[repeated] = replacement
            children[slot] = tuple(parts)
    if replacement is None:
        return None
    if repeated is None:
        children[slot] = replacement
    try:
        return root.rebuild(children)
    except TypeError, ValueError, LexicError:
        return None
