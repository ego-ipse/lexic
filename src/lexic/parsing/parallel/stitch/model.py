"""Type-aware routes and immutable replacement inside grammar models."""

from __future__ import annotations

from typing import Any, NamedTuple, cast

from lexic.exceptions import LexicError
from lexic.ir import (
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNamedTuple,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTuple,
)
from lexic.model import GrammarModel
from lexic.parsing.fold import ModelFold, RuleFold
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.discovery.shapes import literal_char, unbounded
from lexic.parsing.pda.core.charsets import CharSet


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
    """Inputs already derived before model-fold binding begins."""

    root: IrAst
    fold: ModelFold
    rule_name: str
    outer_arm: tuple[IrItem, ...]
    candidate: tuple[int, str, str, str, str]


def _boundary_slots(
    arm: tuple[IrItem, ...], before: int, after: int, config: RuleFold
) -> tuple[int | None, int | None]:
    """Model slots for the wrapper refs immediately around a recurrence."""
    begin = (
        field_slot(config, before)
        if before >= 0 and _ref_at(arm, before) is not None
        else None
    )
    end = (
        field_slot(config, after)
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


def _configured_plan(source: _PlanInput) -> RegionPlan | None:
    """Bind a derived recurrence to exact generated model slots/classes."""
    items_at, items_name, tail_name, head_name, separator = source.candidate
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
    begin, end = _boundary_slots(
        source.outer_arm, items_at - 1, items_at + 1, outer_cfg
    )
    boundary = _boundary_charsets(
        source.root,
        source.outer_arm,
        items_at - 1,
        items_at + 1,
    )
    return RegionPlan(
        root=source.root,
        head_rule=head_name,
        separator=separator,
        outer_type=cast(type[GrammarModel], kinds[0]),
        items_type=cast(type[GrammarModel], kinds[1]),
        tail_type=cast(type[GrammarModel], kinds[2]),
        outer_begin=begin,
        outer_skip=boundary[0],
        outer_items=cast(int, slots[0]),
        outer_end=end,
        outer_trail=boundary[1],
        items_head=cast(int, slots[1]),
        items_rest=cast(int, slots[2]),
        tail_head=cast(int, slots[3]),
    )


class _DirectInput(NamedTuple):
    """Inputs for binding a recurrence held directly by its bracket rule."""

    root: IrAst
    fold: ModelFold
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
    outer_cfg: RuleFold, tail_cfg: RuleFold, head_at: int
) -> _DirectBinding | None:
    """Bind direct model classes and slots, all-or-nothing."""
    kinds = model_type(outer_cfg), model_type(tail_cfg)
    slots = (
        field_slot(outer_cfg, head_at),
        field_slot(outer_cfg, head_at + 1),
        field_slot(tail_cfg, 1),
    )
    if any(kind is None for kind in kinds) or any(slot is None for slot in slots):
        return None
    outer_type, tail_type = cast(tuple[type[GrammarModel], ...], kinds)
    head_slot, rest_slot, tail_head = cast(tuple[int, ...], slots)
    return _DirectBinding(outer_type, tail_type, head_slot, rest_slot, tail_head)


def _direct_plan(source: _DirectInput) -> RegionPlan | None:
    """Bind a bracket rule that carries ``head tail*`` on itself."""
    head_at, tail_name, head_name, separator = source.candidate
    outer_cfg = source.fold.config.get(source.rule_name)
    tail_cfg = source.fold.config.get(tail_name)
    if outer_cfg is None or tail_cfg is None:
        return None
    bound = _direct_binding(outer_cfg, tail_cfg, head_at)
    if bound is None:
        return None
    begin, end = _boundary_slots(source.outer_arm, head_at - 1, head_at + 2, outer_cfg)
    boundary = _boundary_charsets(
        source.root,
        source.outer_arm,
        head_at - 1,
        head_at + 2,
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
    tuple[int, int, str], tuple[IrAst, ModelFold, RegionPlan | None]
] = {}
"""Per-product region plans. Strong grammar/fold references pin identity.

The rooted grammar owns compiled parser tables and worker replicas. Rebuilding
it per document made every split a cold compile and discarded every supposedly
warm replica, dwarfing the parse at benchmark scale.
"""


def derive_plan(grammar: IrAst, fold: ModelFold, rule_name: str) -> RegionPlan | None:
    """Derive the unique repeated-items child of one bracket rule.

    Brackets and whitespace may be referenced wrapper rules or inline grammar
    items. Only the items/tail recurrence is essential. Exact three-reference
    wrappers additionally expose their boundary fields for source restoration.
    """
    key = (id(grammar), id(fold), rule_name)
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
                    fold,
                    rule_name,
                    outer_arm,
                    candidates[0],
                )
            )
        elif outer_arm is not None and len(direct) == 1:
            plan = _direct_plan(
                _DirectInput(root, fold, rule_name, outer_arm, direct[0])
            )
        else:
            plan = None
        entry = (grammar, fold, plan)
        _REGION_PLANS[key] = entry
    return entry[2]


def region_items(model: GrammarModel, plan: RegionPlan) -> GrammarModel | None:
    """The region's items child, guarded by exact generated class."""
    if model.__class__ is not plan.outer_type:
        return None
    if plan.outer_items < 0:
        return model if model.__class__ is plan.items_type else None
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


def stitch_terminated[M: IrNamedTuple](chunks: list[M]) -> M | None:
    """Concatenate whole-unit chunks; ``None`` = shape surprise.

    Each chunk is a document of complete units, so the container's single
    repetition field is the concatenation — no node is rebuilt or rebased.

    The model product stores repeated fields as exact plain tuples. Exact type
    guards keep tuple-shaped IR maps out without requiring the retired
    reduction product's ``IrTuple`` representation.
    """
    sequences = []
    for chunk in chunks:
        fields = tuple(chunk)
        if len(fields) != 1 or fields[0].__class__ is not tuple:
            return None
        sequences.extend(fields[0])
    return chunks[0].rebuild(cast(Any, [tuple(sequences)]))


def _stitch_separated(
    chunks: list[GrammarModel], lead_models: list[tuple]
) -> GrammarModel | None:
    """Rebuild the container from chunk models; ``None`` = shape surprise."""
    heads = [tuple(chunk)[0] for chunk in chunks]
    rests = [tuple(chunk)[1] for chunk in chunks]
    template = next((rest[0] for rest in rests if rest), None)
    if template is None or len(tuple(template)) != len(lead_models[0]) + 1:
        return None
    merged = list(rests[0])
    for k in range(1, len(chunks)):
        merged.append(template.rebuild([*lead_models[k - 1], heads[k]]))
        merged.extend(rests[k])
    return chunks[0].rebuild([heads[0], IrTuple(*merged)])


def _wrapper_route[M: IrNamedTuple](
    wrappers: tuple[str, ...], fold: ModelFold[M]
) -> tuple[tuple[int, None], ...] | None:
    """Model-child route corresponding to a plan's sole-ref wrappers."""
    route: list[tuple[int, None]] = []
    for name in wrappers:
        config = fold.config.get(name)
        slot = field_slot(config, 0) if config is not None else None
        if slot is None:
            return None
        route.append((slot, None))
    return tuple(route)


def _at_route(
    root: GrammarModel, route: tuple[tuple[int, None], ...]
) -> GrammarModel | None:
    """The model below an isolated head-reference wrapper route."""
    node = root
    for slot, _repeated in route:
        children = node.children()
        if slot >= len(children):
            return None
        if any(
            value not in (None, (), "")
            for at, value in enumerate(children)
            if at != slot
        ):
            return None
        child = children[slot]
        if not isinstance(child, GrammarModel):
            return None
        node = child
    return node


def stitch_routed[M: IrNamedTuple](
    chunks: list[M],
    lead_models: list[tuple],
    wrappers: tuple[str, ...],
    fold: ModelFold[M],
) -> M | None:
    """Merge a separated container and rebuild its sole-ref start wrappers."""
    route = _wrapper_route(wrappers, fold)
    if route is None or any(not isinstance(chunk, GrammarModel) for chunk in chunks):
        return None
    roots = cast(list[GrammarModel], chunks)
    containers = [_at_route(root, route) for root in roots]
    if any(container is None for container in containers):
        return None
    merged = _stitch_separated(cast(list[GrammarModel], containers), lead_models)
    if merged is None:
        return None
    rebuilt = splice(roots[0], route, merged) if route else merged
    return cast(M, rebuilt)


def _vacant(value: IrSelf) -> bool:
    """Whether a model child carries nothing — the off-route empty test."""
    return value in (None, (), "")


def _heads_owned(kids: list[list], head: list[int]) -> bool:
    """Whether only the first piece carries the envelope's head fields.

    A later piece that parsed something into the head is not a continuation of
    anything: the head belongs to the document's opening edge, and a piece
    claiming one has read a boundary differently than the split did. TAILS are
    not asked the same question — a non-final piece legitimately absorbs the
    trailing noise a cut left it, and :func:`envelope_tails` moves it.
    """
    return not any(
        any(not _vacant(fields[slot]) for slot in head) for fields in kids[1:]
    )


def _rendered(value: IrSelf) -> str:
    """The source text a model child stands for."""
    if isinstance(value, GrammarModel):
        return value.to_text()
    if isinstance(value, str):
        return value
    if isinstance(value, tuple):
        return "".join(_rendered(item) for item in value)
    return ""


def _emptied(value: IrSelf) -> IrSelf:
    """The same child with nothing in it, keeping the shape its slot expects.

    An absent model child is plain ``None`` on this path, an absent run the
    empty tuple, an absent span the empty string — the engine's own spelling
    of absence, which :func:`_vacant` reads back.
    """
    if isinstance(value, GrammarModel):
        return cast(IrSelf, None)
    if isinstance(value, str):
        return cast(IrSelf, "")
    return cast(IrSelf, () if isinstance(value, tuple) else None)


def envelope_tails[M: IrNamedTuple](
    chunks: list[M], shape, fold: ModelFold[M]
) -> tuple[list[str], list[M]] | None:
    """Move each non-final piece's trailing noise out of it, as text.

    A cut lands on the mark, but a separator can BEGIN before one — an ABNF
    comment IS a line ending, so ``rule ; note`` hands the comment to the
    separator and the newline that closes it to the cut. The piece parses that
    trailing run into its own tail fields; this renders exactly those fields
    back to text for the lead to reparse, and returns the piece without them.

    :returns: ``(trailing text per non-final piece, pieces with tails emptied)``,
        or ``None`` when the container has no readable field map.
    """
    config = fold.config.get(shape.container)
    if config is None:
        return None
    tail = [field_slot(config, at) for at in shape.tail]
    if None in tail:
        return None
    slots = cast(list[int], tail)
    texts: list[str] = []
    trimmed: list[M] = []
    for at, chunk in enumerate(chunks):
        if at == len(chunks) - 1:
            trimmed.append(chunk)
            continue
        fields = list(chunk.children())
        texts.append("".join(_rendered(fields[slot]) for slot in slots))
        for slot in slots:
            fields[slot] = _emptied(fields[slot])
        trimmed.append(cast(M, chunk.rebuild(fields)))
    return texts, trimmed


def stitch_envelope[M: IrNamedTuple](
    chunks: list[M], leads: list, shape, fold: ModelFold[M]
) -> M | None:
    """Rebuild an envelope container from its pieces; ``None`` = shape surprise.

    The first piece owns the head fields and the last owns the tail; every
    piece contributes its own repeated run, joined by the separator each cut
    handed back. A lead reparsed with a witness unit already IS an item model,
    so the join swaps the witness for the unit the next piece really parsed.
    """
    config = fold.config.get(shape.container)
    if config is None or len(chunks) != len(leads) + 1:
        return None
    core = field_slot(config, shape.core)
    rest = field_slot(config, shape.core + 1)
    head = [field_slot(config, at) for at in shape.head]
    tail = [field_slot(config, at) for at in shape.tail]
    if core is None or rest is None or None in head or None in tail:
        return None
    kids = [list(chunk.children()) for chunk in chunks]
    if not _heads_owned(kids, cast(list[int], head)):
        return None
    return _joined(chunks, kids, leads, (core, rest, cast(list[int], tail)))


def _joined[M: IrNamedTuple](
    chunks: list[M], kids: list[list], leads: list, slots: tuple[int, int, list[int]]
) -> M | None:
    """Concatenate the pieces' runs through their rebuilt separators."""
    core, rest, tail = slots
    merged: list[IrSelf] = list(kids[0][rest] or ())
    for at in range(1, len(chunks)):
        lead = leads[at - 1]
        if not isinstance(lead, GrammarModel):
            return None
        fields = list(lead.children())
        fields[-1] = kids[at][core]
        merged.append(lead.rebuild(fields))
        merged.extend(kids[at][rest] or ())
    out = list(kids[0])
    out[rest] = tuple(merged)
    for slot in tail:
        out[slot] = kids[-1][slot]
    return cast(M, chunks[0].rebuild(out))
