"""One bracket rule's model-bearing region plan, derived once per product.

The DERIVATION half of the structural stitch: which repeated-items child a
bracket rule has, which generated classes and field slots that recurrence
binds to, and which finite characters the arms around it own. Its own module
because the answer is derived once per grammar and product and then reused,
while :mod:`~lexic.parsing.parallel.stitch.model` spends it on every document.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrCharClass, IrItem, IrLiteral, IrRule, IrRuleRef
from lexic.model import GrammarModel
from lexic.parsing.caches import adopt, memo
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.discovery.shapes import literal_char, unbounded
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.product import RuleRoutine

__all__ = [
    "RegionPlan",
    "RegionWork",
    "derive_plan",
    "field_slot",
    "model_type",
]


class RegionPlan(NamedTuple):
    """The model-bearing shape of one bracketed region rule."""

    root: IrAst
    head_rule: str
    separator: str
    outer_type: type[GrammarModel]
    items_type: type[GrammarModel]
    tail_type: type[GrammarModel]
    outer_begin: int | None
    outer_skip: frozenset[str]
    outer_items: int
    outer_end: int | None
    outer_trail: frozenset[str]
    items_head: int
    items_rest: int
    tail_head: int


class RegionWork(NamedTuple):
    """One chosen region, its balanced source pieces, and stitch plan."""

    region: Region
    parts: list[str]
    cuts: list[int]
    plan: RegionPlan


def model_type(routine: RuleRoutine | None) -> type[GrammarModel] | None:
    """The generated class this rule constructs, or ``None`` — refused, not assumed."""
    construction = None if routine is None else routine.construction
    call = None if construction is None else construction.call
    if isinstance(call, type) and issubclass(call, GrammarModel):
        return call
    return None


def field_slot(routine: RuleRoutine, item: int) -> int | None:
    """The model-child slot from grammar item ``item`` — its rank among the captures."""
    ordered = sorted(capture.slot for capture in routine.captures)
    return next((rank for rank, slot in enumerate(ordered) if slot == item), None)


def _single_arm(rule: IrRule) -> tuple[IrItem, ...] | None:
    """The items of a rule's sole arm, when it has exactly one."""
    return tuple(rule.body[0]) if len(rule.body) == 1 else None


def _ref_at(items: tuple[IrItem, ...], at: int) -> str | None:
    """The rule reference at one arm position, ignoring its quantifier."""
    atom = items[at].atom
    return str(atom) if isinstance(atom, IrRuleRef) else None


def _candidate(
    rules: dict[str, IrRule], outer_arm: tuple[IrItem, ...], at: int
) -> tuple[str, str, str, str] | None:
    """The items/tail recurrence rooted at one outer-arm position."""
    items_name = _ref_at(outer_arm, at)
    items_rule = rules.get(items_name or "")
    items_arm = _single_arm(items_rule) if items_rule is not None else None
    if items_name is None or items_arm is None or len(items_arm) != 2:
        return None
    head, tail_name = _ref_at(items_arm, 0), _ref_at(items_arm, 1)
    tail_rule = rules.get(tail_name or "")
    tail_arm = _single_arm(tail_rule) if tail_rule is not None else None
    separator = (
        literal_char(tail_arm[0], rules)
        if tail_arm is not None and len(tail_arm) == 2
        else None
    )
    valid_tail = (
        tail_arm is not None and len(tail_arm) == 2 and _ref_at(tail_arm, 1) == head
    )
    if head is None or tail_name is None or not unbounded(items_arm[1]):
        return None
    return (
        (items_name, tail_name, head, separator) if valid_tail and separator else None
    )


def _direct_candidate(
    rules: dict[str, IrRule], outer_arm: tuple[IrItem, ...], at: int
) -> tuple[str, str, str] | None:
    """A direct ``head tail*`` recurrence at two outer-arm positions."""
    if at + 1 >= len(outer_arm):
        return None
    head, tail_name = _ref_at(outer_arm, at), _ref_at(outer_arm, at + 1)
    tail_rule = rules.get(tail_name or "")
    tail_arm = _single_arm(tail_rule) if tail_rule is not None else None
    separator = (
        literal_char(tail_arm[0], rules)
        if tail_arm is not None and len(tail_arm) == 2
        else None
    )
    repeats = unbounded(outer_arm[at + 1])
    returns_head = (
        tail_arm is not None and len(tail_arm) == 2 and _ref_at(tail_arm, 1) == head
    )
    if head and tail_name and separator and repeats and returns_head:
        return tail_name, head, separator
    return None


class _PlanInput(NamedTuple):
    """Inputs already derived before model-product binding begins."""

    root: IrAst
    binding: ModelExecutable
    rule_name: str
    outer_arm: tuple[IrItem, ...]
    candidate: tuple[int, str, str, str, str]


def _boundary_slots(
    arm: tuple[IrItem, ...], before: int, after: int, routine: RuleRoutine
) -> tuple[int | None, int | None]:
    """Model slots for the wrapper refs immediately around a recurrence."""
    begin = (
        field_slot(routine, before)
        if before >= 0 and _ref_at(arm, before) is not None
        else None
    )
    end = (
        field_slot(routine, after)
        if after < len(arm) and _ref_at(arm, after) is not None
        else None
    )
    return begin, end


def _finite_chars(
    item: IrItem, rules: dict[str, IrRule], seen: frozenset[str] = frozenset()
) -> frozenset[str]:
    """Finite characters emitted by a boundary item; co-finite means unknown."""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return frozenset(str(atom))
    if isinstance(atom, IrCharClass):
        chars = CharSet.from_charclass(atom)
        return frozenset() if chars.negated else chars.chars
    if not isinstance(atom, IrRuleRef) or str(atom) in seen:
        return frozenset()
    name = str(atom)
    rule = rules.get(name)
    if rule is None:
        return frozenset()
    return frozenset().union(
        *(
            _finite_chars(inner, rules, seen | {name})
            for arm in rule.body
            for inner in arm
        )
    )


def _boundary_charsets(
    root: IrAst, arm: tuple[IrItem, ...], before: int, after: int
) -> tuple[frozenset[str], frozenset[str]]:
    """Finite source characters owned by the arms around one recurrence."""
    rules = {str(rule.name): rule for rule in root.rules}
    opening = _finite_chars(arm[before], rules) if before >= 0 else frozenset()
    closing = _finite_chars(arm[after], rules) if after < len(arm) else frozenset()
    return opening, closing


class _ConfiguredBinding(NamedTuple):
    """Validated model classes and slots for one configured recurrence."""

    outer_type: type[GrammarModel]
    items_type: type[GrammarModel]
    tail_type: type[GrammarModel]
    items_slot: int
    head_slot: int
    rest_slot: int
    tail_head: int


def _configured_binding(
    outer_pr: RuleRoutine, items_pr: RuleRoutine, tail_pr: RuleRoutine, items_at: int
) -> _ConfiguredBinding | None:
    """Bind a configured recurrence's classes and slots, all-or-nothing."""
    outer_type = model_type(outer_pr)
    items_type = model_type(items_pr)
    tail_type = model_type(tail_pr)
    at = field_slot(outer_pr, items_at)
    head = field_slot(items_pr, 0)
    rest = field_slot(items_pr, 1)
    tail = field_slot(tail_pr, 1)
    if outer_type is None or items_type is None or tail_type is None:
        return None
    if at is None or head is None or rest is None or tail is None:
        return None
    return _ConfiguredBinding(outer_type, items_type, tail_type, at, head, rest, tail)


def _configured_plan(source: _PlanInput) -> RegionPlan | None:
    """Bind a derived recurrence to exact generated model slots/classes."""
    items_at, items_name, tail_name, head_name, separator = source.candidate
    routines = source.binding.routines
    outer_pr = routines.get(source.rule_name)
    items_pr = routines.get(items_name)
    tail_pr = routines.get(tail_name)
    if outer_pr is None or items_pr is None or tail_pr is None:
        return None
    bound = _configured_binding(outer_pr, items_pr, tail_pr, items_at)
    if bound is None:
        return None
    begin, end = _boundary_slots(source.outer_arm, items_at - 1, items_at + 1, outer_pr)
    boundary = _boundary_charsets(
        source.root, source.outer_arm, items_at - 1, items_at + 1
    )
    return RegionPlan(
        root=source.root,
        head_rule=head_name,
        separator=separator,
        outer_type=bound.outer_type,
        items_type=bound.items_type,
        tail_type=bound.tail_type,
        outer_begin=begin,
        outer_skip=boundary[0],
        outer_items=bound.items_slot,
        outer_end=end,
        outer_trail=boundary[1],
        items_head=bound.head_slot,
        items_rest=bound.rest_slot,
        tail_head=bound.tail_head,
    )


class _DirectInput(NamedTuple):
    """Inputs for binding a recurrence held directly by its bracket rule."""

    root: IrAst
    binding: ModelExecutable
    rule_name: str
    outer_arm: tuple[IrItem, ...]
    candidate: tuple[int, str, str, str]


class _DirectBinding(NamedTuple):
    """Validated model classes and slots for one direct recurrence."""

    outer_type: type[GrammarModel]
    tail_type: type[GrammarModel]
    head_slot: int
    rest_slot: int
    tail_head: int


def _direct_binding(
    outer_pr: RuleRoutine, tail_pr: RuleRoutine, head_at: int
) -> _DirectBinding | None:
    """Bind direct model classes and slots, all-or-nothing."""
    outer_type = model_type(outer_pr)
    tail_type = model_type(tail_pr)
    head = field_slot(outer_pr, head_at)
    rest = field_slot(outer_pr, head_at + 1)
    tail = field_slot(tail_pr, 1)
    if outer_type is None or tail_type is None:
        return None
    if head is None or rest is None or tail is None:
        return None
    return _DirectBinding(outer_type, tail_type, head, rest, tail)


def _direct_plan(source: _DirectInput) -> RegionPlan | None:
    """Bind a bracket rule that carries ``head tail*`` on itself."""
    head_at, tail_name, head_name, separator = source.candidate
    outer_pr = source.binding.routines.get(source.rule_name)
    tail_pr = source.binding.routines.get(tail_name)
    if outer_pr is None or tail_pr is None:
        return None
    bound = _direct_binding(outer_pr, tail_pr, head_at)
    if bound is None:
        return None
    begin, end = _boundary_slots(source.outer_arm, head_at - 1, head_at + 2, outer_pr)
    boundary = _boundary_charsets(
        source.root, source.outer_arm, head_at - 1, head_at + 2
    )
    return RegionPlan(
        root=source.root,
        head_rule=head_name,
        separator=separator,
        outer_type=bound.outer_type,
        items_type=bound.outer_type,
        tail_type=bound.tail_type,
        outer_begin=begin,
        outer_skip=boundary[0],
        outer_items=-1,
        outer_end=end,
        outer_trail=boundary[1],
        items_head=bound.head_slot,
        items_rest=bound.rest_slot,
        tail_head=bound.tail_head,
    )


_REGION_PLANS: dict[
    tuple[int, int, str], tuple[IrAst, ModelExecutable, RegionPlan | None]
] = memo({}, 0, 1)
"""Per-product region plans. Strong grammar/binding references pin identity.

The rooted grammar owns compiled parser tables and worker replicas. Rebuilding
it per document made every split a cold compile and discarded every supposedly
warm replica, dwarfing the parse at benchmark scale.
"""


def derive_plan(
    grammar: IrAst, binding: ModelExecutable, rule_name: str
) -> RegionPlan | None:
    """Derive the unique repeated-items child of one bracket rule.

    Brackets and whitespace may be referenced wrapper rules or inline grammar
    items. Only the items/tail recurrence is essential. Exact three-reference
    wrappers additionally expose their boundary fields for source restoration.
    """
    key = (id(grammar), id(binding), rule_name)
    entry = _REGION_PLANS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        outer = rules.get(rule_name)
        outer_arm = _single_arm(outer) if outer is not None else None
        candidates = (
            [
                (at, *candidate)
                for at in range(len(outer_arm))
                if (candidate := _candidate(rules, outer_arm, at)) is not None
            ]
            if outer_arm is not None
            else []
        )
        direct = (
            [
                (at, *candidate)
                for at in range(len(outer_arm))
                if (candidate := _direct_candidate(rules, outer_arm, at)) is not None
            ]
            if outer_arm is not None
            else []
        )
        root = IrAst(grammar.rules, rule_name)
        if outer_arm is not None and len(candidates) == 1:
            plan = _configured_plan(
                _PlanInput(
                    root,
                    binding,
                    rule_name,
                    outer_arm,
                    candidates[0],
                )
            )
        elif outer_arm is not None and len(direct) == 1:
            plan = _direct_plan(
                _DirectInput(root, binding, rule_name, outer_arm, direct[0])
            )
        else:
            plan = None
        entry = (grammar, binding, plan)
        _REGION_PLANS[key] = entry
        adopt(id(grammar), root)  # the witness memo keys on the rooted grammar
    return entry[2]
