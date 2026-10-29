"""Type-aware routes and immutable replacement inside grammar models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from lexic.exceptions import EngineInvariantError, LexicError
from lexic.ir import Bound, IrNamedTuple, IrSelf, is_plain_tuple
from lexic.model import GrammarModel
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.parallel.stitch.plan import RegionPlan, field_slot


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
    """One items node's head and plain-tuple repeated tails — for a terminated
    run (``plan.ends``), its first unit and the rest of its run."""
    children = items.children()
    if max(plan.items_head, plan.items_rest) >= len(children):
        return None
    head, rest = children[plan.items_head], children[plan.items_rest]
    if plan.ends:
        if not is_plain_tuple(rest) or not rest:
            return None
        units = cast(tuple[GrammarModel, ...], rest)
        return units[0], units[1:]
    if not isinstance(head, GrammarModel) or not is_plain_tuple(rest):
        return None
    tails = cast(tuple[object, ...], rest)
    if any(tail.__class__ is not plan.tail_type for tail in tails):
        return None
    return head, cast(tuple[GrammarModel, ...], tails)


type ModelStep = tuple[int, int | None]
"""One model-child slot and, for a repeated field, its tuple index."""


def sole_routes(
    root: GrammarModel, needles: list[GrammarModel]
) -> list[tuple[ModelStep, ...] | None]:
    """Each needle's unique exact-class/equal-value route below ``root``.

    ONE walk for every needle: a walk per needle would cost regions times
    shell size, which outgrows the sequential parse at a few dozen regions.

    :param root: The shell model to search.
    :param needles: The regions' distinct items-node stand-ins.
    :returns: Per needle, its non-root route, or ``None`` on absence or
        collision.
    """
    by_class: dict[type, list[int]] = {}
    for at, needle in enumerate(needles):
        by_class.setdefault(needle.__class__, []).append(at)
    hits: list[list[tuple[ModelStep, ...]]] = [[] for _needle in needles]
    stack: list[tuple[GrammarModel, tuple[ModelStep, ...]]] = [(root, ())]
    while stack:
        node, route = stack.pop()
        for at in by_class.get(node.__class__, ()):
            if node == needles[at]:
                hits[at].append(route)
        for slot, child in enumerate(node.children()):
            if isinstance(child, GrammarModel):
                stack.append((child, (*route, (slot, None))))
            elif is_plain_tuple(child):
                parts = cast(tuple[object, ...], child)
                stack.extend(
                    (part, (*route, (slot, at)))
                    for at, part in enumerate(parts)
                    if isinstance(part, GrammarModel)
                )
    return [found[0] if len(found) == 1 and found[0] else None for found in hits]


def held_route(
    model: GrammarModel, plan: RegionPlan, item: int, needle: GrammarModel
) -> tuple[ModelStep, ...] | None:
    """The route to ``needle`` inside a piece's ``item``-th item.

    The piece's items are reached by the plan's slots, so only that one item
    is searched — a piece is about a worker's share of the document, and
    walking all of it per held region would cost the document again.

    :returns: The route from the piece's root, or ``None`` on a shape surprise,
        absence or collision.
    """
    found = _item_at(model, plan, item)
    if found is None:
        return None
    base, inner = found
    if inner.__class__ is needle.__class__ and inner == needle:
        return base
    below = sole_routes(inner, [needle])[0]
    return None if below is None else (*base, *below)


def _item_at(
    model: GrammarModel, plan: RegionPlan, item: int
) -> tuple[tuple[ModelStep, ...], GrammarModel] | None:
    """A piece's ``item``-th item model, and the route to it."""
    items = region_items(model, plan)
    shaped = head_rest(items, plan) if items is not None else None
    if shaped is None or not 0 <= item <= len(shaped[1]):
        return None
    base: tuple[ModelStep, ...] = (
        () if plan.outer_items < 0 else ((plan.outer_items, None),)
    )
    head, tails = shaped
    if item == 0:
        return (*base, (plan.items_head, None)), head
    children = tails[item - 1].children()
    inner = children[plan.tail_head] if plan.tail_head < len(children) else None
    if not isinstance(inner, GrammarModel):
        return None
    return (*base, (plan.items_rest, item - 1), (plan.tail_head, None)), inner


@dataclass(frozen=True, slots=True)
class Reading:
    """How :func:`read_route` reads a route — one of the three readings below,
    never built by a caller. Slotted rather than a tuple, because the walk reads
    its flags per step and a slot read is the fast one.

    :ivar sole_runs: A run step needs a run of exactly one element.
    :ivar strict: A slot the model does not have raises rather than declines.
    :ivar isolated: Every other child of a step's node must be empty.
    """

    sole_runs: bool
    strict: bool
    isolated: bool


FOUND = Reading(sole_runs=False, strict=False, isolated=False)
"""A route :func:`sole_routes` found in the model: a run step indexes a run of
any length (json's 800 records), and anything missing declines."""

PREDICTED = Reading(sole_runs=True, strict=True, isolated=False)
"""A route derived from the grammar (a routed interior's, a folded spine's).

**Every run step must hold exactly one element.** ``splice`` bounds a run index
but never checks arity, so a step naming element 0 of a run of three would
rewrite the first and leave the other two: a wrong model rather than a refusal.
One unit is true by construction in a PIECE, not in the whole model an
intermediate step runs over. A slot the model does not have means the chain and
the model disagree about the grammar, not a document shape, so it raises."""

WRAPPED = Reading(sole_runs=False, strict=False, isolated=True)
"""A separated plan's sole-reference start wrappers: each step's node must hold
nothing beside the child it is read through, or the wrapper is not the plain
shell the merge rebuilds."""


def read_route(
    node: GrammarModel, route: tuple[ModelStep, ...], reading: Reading
) -> GrammarModel | None:
    """The model at ``route`` below ``node`` under ``reading``, or ``None``
    when the shape surprises.

    Each child is checked for a model as the walk steps into it, so the node
    in hand is always one and the answer needs no check of its own.

    :raises EngineInvariantError: Under a strict reading, at a slot the model
        does not have.
    """
    if not route:
        return node  # a separated plan with no wrapper: the root is the container
    isolated = reading.isolated  # read per step otherwise
    current = node
    for slot, index in route:
        children = current.children()
        if slot >= len(children):
            if reading.strict:
                raise EngineInvariantError(
                    f"routed chain names slot {slot} of "
                    f"{type(current).__name__}, which has {len(children)}"
                )
            return None
        if (
            isolated
            and len(children) > 1
            and any(
                value not in (None, (), "")
                for at, value in enumerate(children)
                if at != slot
            )
        ):
            return None
        held: object = children[slot]
        if index is not None:
            if not is_plain_tuple(held):
                return None
            if reading.sole_runs:  # a run of two was never one run: decline
                held = held[0] if len(held) == 1 else None
            else:
                held = held[index] if index < len(held) else None
        if not isinstance(held, GrammarModel):
            return None
        current = held
    return current


def overlaid(node: GrammarModel, overlay: Mapping[int, Bound]) -> GrammarModel | None:
    """``node`` rebuilt with the given slots replaced — same class, or ``None``."""
    children: list[Bound] = list(node.children())
    if any(slot >= len(children) for slot in overlay):
        return None
    for slot, value in overlay.items():
        children[slot] = value
    try:
        out = node.rebuild(children)
    except TypeError, ValueError, LexicError:
        return None
    return out if out.__class__ is node.__class__ else None


def _nested(
    child: object, route: tuple[ModelStep, ...], value: GrammarModel
) -> GrammarModel | None:
    """Replacement at or below one already selected model child."""
    if not isinstance(child, GrammarModel):
        return None
    return value if len(route) == 1 else splice(child, route[1:], value)


def splice[M: GrammarModel](
    root: M, route: tuple[ModelStep, ...], value: GrammarModel
) -> M | None:
    """Replace the model at ``route``, immutably rebuilding its ancestors.

    Generic in the root because the rebuild IS the root's own type: a model
    rebuilds to its own class, so a caller holding a start-rule model gets one
    back rather than the protocol's base.

    :param root: The current shell model.
    :param route: A route returned by :func:`sole_routes`.
    :param value: The replacement items node.
    :returns: The rebuilt model, or ``None`` on a shape surprise.
    """
    if not route:
        return None
    slot, repeated = route[0]
    children: list[Bound] = list(root.children())
    if slot >= len(children):
        return None
    child = children[slot]
    if repeated is None:
        replacement = _nested(child, route, value)
    else:
        if not is_plain_tuple(child) or repeated >= len(child):
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
        if len(fields) != 1 or not is_plain_tuple(fields[0]):
            return None
        sequences.extend(fields[0])
    return chunks[0].rebuild(cast(Any, [tuple(sequences)]))


def _stitch_separated(
    chunks: list[GrammarModel], lead_models: list[tuple]
) -> GrammarModel | None:
    """Rebuild the container from chunk models; ``None`` = shape surprise.

    The repetition field is a PLAIN tuple, as the model product builds it and
    as :func:`~lexic.ir.spine.records.is_plain_tuple` reads it. An ``IrTuple``
    here compared and rendered the same, so text and structure matched a
    sequential parse — and then failed the run test that decides whether a
    field is a repetition at all.
    """
    heads = [tuple(chunk)[0] for chunk in chunks]
    rests = [tuple(chunk)[1] for chunk in chunks]
    template = next((rest[0] for rest in rests if rest), None)
    if template is None or len(tuple(template)) != len(lead_models[0]) + 1:
        return None
    merged = list(rests[0])
    for k in range(1, len(chunks)):
        merged.append(template.rebuild([*lead_models[k - 1], heads[k]]))
        merged.extend(rests[k])
    return chunks[0].rebuild([heads[0], tuple(merged)])


def _wrapper_route[M: IrNamedTuple](
    wrappers: tuple[str, ...], binding: ModelExecutable[M]
) -> tuple[tuple[int, None], ...] | None:
    """Model-child route corresponding to a plan's sole-ref wrappers."""
    route: list[tuple[int, None]] = []
    for name in wrappers:
        routine = binding.routines.get(name)
        slot = field_slot(routine, 0) if routine is not None else None
        if slot is None:
            return None
        route.append((slot, None))
    return tuple(route)


def stitch_routed[M: IrNamedTuple](
    chunks: list[M],
    lead_models: list[tuple],
    wrappers: tuple[str, ...],
    binding: ModelExecutable[M],
) -> M | None:
    """Merge a separated container and rebuild its sole-ref start wrappers."""
    route = _wrapper_route(wrappers, binding)
    if route is None or any(not isinstance(chunk, GrammarModel) for chunk in chunks):
        return None
    roots = cast(list[GrammarModel], chunks)
    containers = [read_route(root, route, WRAPPED) for root in roots]
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
    chunks: list[M], shape, binding: ModelExecutable[M]
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
    routine = binding.routines.get(shape.container)
    if routine is None:
        return None
    tail = [field_slot(routine, at) for at in shape.tail]
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
    chunks: list[M], leads: list, shape, binding: ModelExecutable[M]
) -> M | None:
    """Rebuild an envelope container from its pieces; ``None`` = shape surprise.

    The first piece owns the head fields and the last owns the tail; every
    piece contributes its own repeated run, joined by the separator each cut
    handed back. A lead reparsed with a witness unit already IS an item model,
    so the join swaps the witness for the unit the next piece really parsed.
    """
    routine = binding.routines.get(shape.container)
    if routine is None or len(chunks) != len(leads) + 1:
        return None
    core = field_slot(routine, shape.core)
    rest = field_slot(routine, shape.core + 1)
    head = [field_slot(routine, at) for at in shape.head]
    tail = [field_slot(routine, at) for at in shape.tail]
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
