"""Rebuild delegated region models and attach them to a small parsed shell.

The expensive recursive heads belong to piece workers.  Boundary tails reuse
an already parsed separator shape when that shape spells exactly the certified
separator, and the enclosing shell uses a grammar-generated shallow head.
Neither path reparses a delegated subtree merely to discover where it belongs.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from itertools import count, islice
from threading import Lock
from typing import NamedTuple

from lexic.exceptions import LexicError
from lexic.generate import generate
from lexic.ir import Bound, IrAst, IrRule
from lexic.model import GrammarModel
from lexic.parsing.caches import memo
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.partition import Division, Unit, units
from lexic.parsing.parallel.stitch.model import (
    ModelStep,
    head_rest,
    held_route,
    model_at,
    overlaid,
    region_items,
    sole_routes,
    splice,
)
from lexic.parsing.parallel.stitch.plan import RegionPlan, RegionWork


class MergeRequest[M](NamedTuple):
    """The parse service and per-document inputs shared by every stitch step."""

    parse: ModelParse[M]
    text: str
    binding: ModelExecutable[M]
    config: ParseConfig

    def run(self, grammar: IrAst, text: str) -> M:
        """Parse one full, piece, boundary, or shell document."""
        return self.parse(grammar, text, self.binding, self.config)


def _replace_tail_head(
    template: GrammarModel, head: GrammarModel, plan: RegionPlan
) -> GrammarModel | None:
    """Reuse a certified one-character separator around a delegated head."""
    children: list[Bound] = list(template.children())
    if plan.tail_head >= len(children):
        return None
    children[plan.tail_head] = head
    try:
        tail = template.rebuild(children)
    except TypeError, ValueError, LexicError:
        return None
    return tail if tail.__class__ is plan.tail_type else None


def _template_lead(template: GrammarModel, plan: RegionPlan) -> str | None:
    """Render only a parsed tail's shallow fields before its delegated head."""
    children = template.children()
    if plan.tail_head >= len(children):
        return None
    parts: list[str] = []
    for child in children[: plan.tail_head]:
        if isinstance(child, GrammarModel):
            parts.append(child.to_text())
        elif isinstance(child, str):
            parts.append(child)
        else:
            return None
    rendered = "".join(parts)
    return (
        rendered if rendered.startswith(plan.separator) else plan.separator + rendered
    )


def _template_tail(
    templates: list[GrammarModel], lead: str, head: GrammarModel, plan: RegionPlan
) -> GrammarModel | None:
    """Reuse an exact shallow lead shape already parsed by a piece worker."""
    template = next(
        (item for item in templates if _template_lead(item, plan) == lead), None
    )
    return _replace_tail_head(template, head, plan) if template is not None else None


def _boundary_lead(
    work: RegionWork, later: GrammarModel, text: str, cut: int
) -> str | None:
    """The cut separator plus noise owned by the later piece's fake opener."""
    lead = work.plan.separator
    begin_at = work.plan.outer_begin
    if begin_at is None:
        return lead
    children = later.children()
    if begin_at >= len(children):
        return None
    begin = children[begin_at]
    if begin is None:
        after = cut + 1
        opener = text[work.region.opener]
        while (
            after < len(text)
            and text[after] != opener
            and text[after] in work.plan.outer_skip
        ):
            after += 1
        return text[cut:after]
    if not isinstance(begin, GrammarModel):
        return None
    before = begin.to_text()
    opener = text[work.region.opener]
    return lead + (before[1:] if before.startswith(opener) else before)


def _shallow_tail[M](
    request: MergeRequest[M],
    work: RegionWork,
    later: GrammarModel,
    head: GrammarModel,
    cut: int,
) -> GrammarModel | None:
    """Parse only a shallow boundary witness, then attach the delegated head."""
    witness = _witness(work.plan, 0)
    lead = _boundary_lead(work, later, request.text, cut)
    if witness is None or lead is None:
        return None
    text = request.text
    open_char, close_char = text[work.region.opener], text[work.region.closer]
    wrapped = open_char + witness + lead + witness + close_char
    try:
        model = request.run(work.plan.root, wrapped)
    except LexicError:
        return None
    if not isinstance(model, GrammarModel):
        return None
    items = region_items(model, work.plan)
    shaped = head_rest(items, work.plan) if items is not None else None
    if shaped is None or len(shaped[1]) != 1:
        return None
    return _replace_tail_head(shaped[1][0], head, work.plan)


class _Joint(NamedTuple):
    """One removed boundary and the already parsed model on either side."""

    later: GrammarModel
    head: GrammarModel
    templates: list[GrammarModel]
    cut: int


def _joint_tail[M](
    request: MergeRequest[M], work: RegionWork, joint: _Joint
) -> GrammarModel | None:
    """Build one shallow boundary around an already delegated head."""
    lead = _boundary_lead(work, joint.later, request.text, joint.cut)
    if lead is None:
        return None
    reused = _template_tail(joint.templates, lead, joint.head, work.plan)
    return (
        reused
        if reused is not None
        else _shallow_tail(
            request,
            work,
            joint.later,
            joint.head,
            joint.cut,
        )
    )


def _joined_tails[M](
    request: MergeRequest[M],
    work: RegionWork,
    models: list[GrammarModel],
    shaped: list[tuple[GrammarModel, tuple[GrammarModel, ...]]],
) -> list[GrammarModel] | None:
    """Join existing tails with each removed separator boundary."""
    merged = list(shaped[0][1])
    templates = [tail for _head, rest in shaped for tail in rest]
    later_parts = zip(models[1:], shaped[1:], strict=True)
    for cut, (later, (head, rest)) in zip(work.cuts, later_parts, strict=True):
        tail = _joint_tail(request, work, _Joint(later, head, templates, cut))
        if tail is None:
            return None
        children = tail.children()
        if (
            work.plan.tail_head >= len(children)
            or children[work.plan.tail_head] != head
        ):
            return None
        merged.append(tail)
        merged.extend(rest)
    return merged


def _merge_items[M](
    request: MergeRequest[M],
    work: RegionWork,
    models: list[GrammarModel],
) -> GrammarModel | None:
    """Join piece item nodes without reparsing already delegated heads."""
    shaped: list[tuple[GrammarModel, tuple[GrammarModel, ...]]] = []
    first_items: GrammarModel | None = None
    for model in models:
        items = region_items(model, work.plan)
        part = head_rest(items, work.plan) if items is not None else None
        if part is None:
            return None
        first_items = first_items or items
        shaped.append(part)
    if first_items is None or len(shaped) != len(work.cuts) + 1:
        return None
    merged = _joined_tails(request, work, models, shaped)
    if merged is None:
        return None
    children: list[Bound] = list(first_items.children())
    children[work.plan.items_rest] = tuple(merged)
    if work.plan.outer_items < 0 and work.plan.outer_end is not None:
        last = models[-1].children()
        if work.plan.outer_end >= len(last):
            return None
        children[work.plan.outer_end] = last[work.plan.outer_end]
    try:
        out = first_items.rebuild(children)
    except TypeError, ValueError, LexicError:
        return None
    return out if out.__class__ is work.plan.items_type else None


_DEPTHS, _SEEDS, _LONGEST = 6, 256, 256
"""The witness draw: depth-major, seed-minor, heads of at most 256 characters.
Wide enough that a head shared by dozens of regions still has distinct texts —
the draw is lazy, so a grammar pays only for the texts a document asks for."""


class _Draw(NamedTuple):
    """One head rule's witness stream so far, where the draw resumes, and the
    lock that makes both one step — so the stream is the same whatever threads
    read it, and witness choice never depends on their timing."""

    rules: dict[str, IrRule]
    texts: list[str]
    at: list[int]
    lock: Lock


_WITNESSES: dict[tuple[int, str], tuple[IrAst, _Draw]] = memo({}, 0)
"""The witness stream per rooted grammar and head rule, with identity pinned."""


def witnesses(plan: RegionPlan) -> Iterator[str]:
    """The head rule's distinct bounded texts, in draw order, drawn as needed."""
    key = (id(plan.root), plan.head_rule)
    entry = _WITNESSES.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in plan.root.rules}
        entry = _WITNESSES.setdefault(key, (plan.root, _Draw(rules, [], [0], Lock())))
    draw = entry[1]
    for index in count():
        text = _drawn(draw, plan.head_rule, index)
        if text is None:
            return
        yield text


def _drawn(draw: _Draw, head: str, index: int) -> str | None:
    """The stream's ``index``-th text, drawing under the lock until it exists."""
    with draw.lock:
        while len(draw.texts) <= index and draw.at[0] < _DEPTHS * _SEEDS:
            depth, seed = divmod(draw.at[0], _SEEDS)
            draw.at[0] += 1
            try:
                text = generate(
                    head, draw.rules, rng=random.Random(seed), max_depth=depth
                )
            except LexicError:
                continue
            if len(text) <= _LONGEST and text not in draw.texts:
                draw.texts.append(text)
        return draw.texts[index] if index < len(draw.texts) else None


def _witness(plan: RegionPlan, index: int) -> str | None:
    """The indexed distinct bounded head, or ``None`` when the draw has fewer."""
    return next(islice(witnesses(plan), index, None), None)


def assign_witnesses[M](
    request: MergeRequest[M], works: list[RegionWork]
) -> list[RegionWork]:
    """Give every region a stand-in its holder cannot confuse — BEFORE any
    piece is parsed, so a region that cannot have one costs nothing.

    The witness stands in for the region's whole interior, and its NEEDLE is
    the items node it parses to: the unit holding it must hold exactly one
    node equal to that. Equal models spell equal text, so a needle whose text
    occurs nowhere else in its holder, nor inside another needle's there, has
    exactly one route in it. Text is the proxy; :func:`sole_routes` still checks. A region
    with no such witness is left undivided: its text returns to its holder,
    which can make an earlier choice collide, so choosing repeats over the
    regions still divided until every one has a witness.

    :returns: The works that keep a witness; empty when none does.
    """
    text, kept = request.text, works
    while kept:
        divided = [Division(work.region, work.cuts) for work in kept]
        blank = units(text, divided, [""] * len(kept))
        holder = {k: unit for unit in blank for k in unit.held}
        taken: dict[int, list[str]] = {}
        assigned = [
            placed
            for k, work in enumerate(kept)
            if (
                placed := _place(
                    request,
                    work,
                    holder[k].text,
                    taken.setdefault(id(holder[k]), []),
                )
            )
            is not None
        ]
        if len(assigned) == len(kept):
            return assigned
        kept = [work for work in kept if any(a.region == work.region for a in assigned)]
    return []


def _place[M](
    request: MergeRequest[M], work: RegionWork, outside: str, taken: list[str]
) -> RegionWork | None:
    """``work`` with the first witness whose needle ``outside`` cannot confuse.

    :param outside: The holding unit's text, the divided interiors blank.
    :param taken: The needles' texts already placed in that unit; this one's
        is added.
    """
    for witness in witnesses(work.plan):
        needle = _needle(request, work, witness)
        spelled = needle.to_text() if needle is not None else None
        if spelled is not None and _unique(spelled, outside, taken):
            taken.append(spelled)
            return work._replace(witness=witness, needle=needle)
    return None


def _needle[M](
    request: MergeRequest[M], work: RegionWork, witness: str
) -> GrammarModel | None:
    """The items node the region's own brackets around ``witness`` parse to."""
    text = request.text
    source = text[work.region.opener] + witness + text[work.region.closer]
    try:
        stand = request.run(work.plan.root, source)
    except LexicError:
        return None
    if not isinstance(stand, GrammarModel):
        return None
    items = region_items(stand, work.plan)
    shaped = head_rest(items, work.plan) if items is not None else None
    return items if shaped is not None else None


def _unique(witness: str, outside: str, taken: list[str]) -> bool:
    """Whether ``witness`` can occur in the shell only where it is placed."""
    if witness in outside:
        return False
    return all(witness not in other and other not in witness for other in taken)


class Attached(NamedTuple):
    """One finished region, ready to lay over its stand-in where it is held.

    :ivar work: The region.
    :ivar overlay: Slot → value on the stand-in's node: the merged items.
    :ivar ends: The first and last pieces, whose edge slots decide the
        region's edges inside its brackets.
    :ivar up: The steps from the stand-in's node down to its needle.
    """

    work: RegionWork
    overlay: dict[int, Bound]
    ends: tuple[GrammarModel, GrammarModel]
    up: tuple[ModelStep, ...]


def stitch_units[M](
    request: MergeRequest[M],
    works: list[RegionWork],
    plan: list[Unit],
    models: list[GrammarModel],
    whole: M,
) -> M | None:
    """Attach every divided region's value where it is held, innermost first.

    ``models`` are the pieces' parses, in ``plan`` order; ``whole`` is the
    shell's, the last unit. A region's pieces first receive the values of the
    regions they hold, then merge into that region's value. A held region
    opens after its holder, so reverse document order finishes every region
    before its holder needs it. Two equal needles in one unit are refused by
    :func:`sole_routes` itself — each is found twice.
    """
    pieces: list[list[int]] = [[] for _work in works]
    for at, unit in enumerate(plan[:-1]):
        pieces[unit.owner].append(at)
    attached: list[Attached | None] = [None] * len(works)
    for index in reversed(range(len(works))):
        region_plan = works[index].plan
        filled = [
            _attach(request, models[at], plan[at], region_plan, attached)
            for at in pieces[index]
        ]
        ready = [model for model in filled if model is not None]
        done = (
            _finish(request, works[index], ready) if len(ready) == len(filled) else None
        )
        if done is None:
            return None
        attached[index] = done
    if not isinstance(whole, GrammarModel):
        return None
    return _attach(request, whole, plan[-1], None, attached)


def _finish[M](
    request: MergeRequest[M], work: RegionWork, models: list[GrammarModel]
) -> Attached | None:
    """What the region's pieces decide about its node: the merged items, and
    — through its first and last pieces — its edges inside the brackets."""
    items = _merge_items(request, work, models)
    plan = work.plan
    if items is None:
        return None
    ends = (models[0], models[-1])
    if plan.outer_items >= 0:
        up: tuple[ModelStep, ...] = ((plan.outer_items, None),)
        return Attached(work, {plan.outer_items: items}, ends, up)
    merged = items.children()
    overlay: dict[int, Bound] = {
        plan.items_head: merged[plan.items_head],
        plan.items_rest: merged[plan.items_rest],
    }
    return Attached(work, overlay, ends, ())


def _attach[M, T: GrammarModel](
    request: MergeRequest[M],
    model: T,
    unit: Unit,
    plan: RegionPlan | None,
    attached: list[Attached | None],
) -> T | None:
    """``model`` with each held region's pieces laid over its stand-in.

    A piece (``plan`` given) is searched only in the item holding each needle;
    the shell has no items, so the whole of it is walked once.
    """
    ready = [done for k in unit.held if (done := attached[k]) is not None]
    needles = [done.work.needle for done in ready]
    if len(ready) != len(unit.held) or None in needles:
        return None
    found = [needle for needle in needles if needle is not None]
    routes = (
        sole_routes(model, found)
        if plan is None
        else [
            held_route(model, plan, item, needle)
            for item, needle in zip(unit.items, found, strict=True)
        ]
    )
    out: T | None = model
    for route, done in zip(routes, ready, strict=True):
        cut = len(route) - len(done.up) if route is not None else -1
        if route is None or out is None or cut < 1 or route[cut:] != done.up:
            return None
        node = model_at(out, route[:cut])
        laid = _laid(request, done, node) if node is not None else None
        out = splice(out, route[:cut], laid) if laid is not None else None
    return out


def _laid[M](
    request: MergeRequest[M], done: Attached, node: GrammarModel
) -> GrammarModel | None:
    """The stand-in's node with the region's items and its true edges.

    An edge slot can straddle a bracket — ``ws "}" ws`` — so its truth is the
    PIECE's part inside the bracket and the HOLDER's outside it: the pieces
    never saw what follows the closer, and the stand-in's own noise may sit
    inside where a real item absorbed the source's. Each edge is built from
    the two slots' children, split at the bracket, and taken only when it
    spells exactly that truth.
    """
    plan, text = done.work.plan, request.text
    region = done.work.region
    overlay = dict(done.overlay)
    for slot, piece, bracket, opening in (
        (plan.outer_begin, done.ends[0], text[region.opener], True),
        (plan.outer_end, done.ends[1], text[region.closer], False),
    ):
        if slot is None:
            continue
        edge = _true_edge(_child(node, slot), _child(piece, slot), bracket, opening)
        if edge is None:
            return None
        overlay[slot] = edge[0]
    return overlaid(node, overlay)


def _child(model: GrammarModel, slot: int) -> Bound:
    """One slot's value, or ``None`` past the model's children."""
    children = model.children()
    return children[slot] if slot < len(children) else None


def _spelled(value: Bound) -> str | None:
    """An edge slot's text: empty when unset, ``None`` when not a model."""
    if value is None:
        return ""
    return value.to_text() if isinstance(value, GrammarModel) else None


def _true_edge(
    held: Bound, pieced: Bound, bracket: str, opening: bool
) -> tuple[Bound] | None:
    """The edge that spells the holder's text beyond ``bracket`` and the
    piece's within it — as a 1-tuple, since an unset edge is ``None`` — or
    ``None`` when no split of the two slots spells it."""
    outer, inner = _spelled(held), _spelled(pieced)
    if outer is None or inner is None:
        return None
    truth = _joined(outer, inner, bracket, opening)
    candidates: list[Bound] = [held, pieced]
    if (
        isinstance(held, GrammarModel)
        and isinstance(pieced, GrammarModel)
        and held.__class__ is pieced.__class__
    ):
        candidates.extend(_splits(held, pieced, opening))
    return next(((c,) for c in candidates if _spelled(c) == truth), None)


def _splits(held: GrammarModel, pieced: GrammarModel, opening: bool) -> list[Bound]:
    """The holder's slot rebuilt with the piece's children on the bracket's
    inner side, at every split point."""
    outer, inner = held.children(), pieced.children()
    out: list[Bound] = []
    for at in range(len(inner) + 1):
        parts = [*outer[:at], *inner[at:]] if opening else [*inner[:at], *outer[at:]]
        try:
            out.append(held.rebuild(parts))
        except TypeError, ValueError, LexicError:
            continue
    return out


def _joined(outer: str, inner: str, bracket: str, opening: bool) -> str:
    """One edge slot's true text: ``outer``'s part beyond the bracket, and
    ``inner``'s part within it — the bracket itself where either spells it."""
    if opening:
        head = outer[: outer.find(bracket) + 1] if bracket in outer else ""
        tail = inner[inner.find(bracket) + 1 :] if bracket in inner else inner
        return head + tail
    head = inner[: inner.rfind(bracket) + 1] if bracket in inner else inner
    tail = outer[outer.rfind(bracket) + 1 :] if bracket in outer else ""
    return head + tail
