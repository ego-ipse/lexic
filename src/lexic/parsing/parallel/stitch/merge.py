"""Rebuild delegated region models and attach them to a small parsed shell.

The expensive recursive heads belong to piece workers.  Boundary tails reuse
an already parsed separator shape when that shape spells exactly the certified
separator, and the enclosing shell uses a grammar-generated shallow head.
Neither path reparses a delegated subtree merely to discover where it belongs.
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
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
from lexic.parsing.parallel.discovery.regions import shell
from lexic.parsing.parallel.stitch.model import (
    head_rest,
    region_items,
    sole_route,
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
) -> list[RegionWork] | None:
    """Give every region a stand-in the shell cannot confuse — BEFORE any piece
    is parsed, so a region that cannot have one costs nothing.

    Two pre-filters, both for LIVENESS — a split that would decline after its
    pieces are parsed is cheaper declined now: a witness whose text occurs
    nowhere else in the shell, nor inside another witness, will not route
    ambiguously there; and one whose stand-in keeps the region's edge noise
    in its edge slots (:func:`_keeps_edges`) will pass :func:`_standin`'s check.
    SOUNDNESS stays with the checks after the parse — :func:`sole_route` and
    :func:`_standin` — since text is only a proxy for model equality. A region
    with no such witness is left undivided: its text returns to the shell,
    which can make an earlier choice collide, so choosing repeats over the
    regions still divided until every one has a witness.

    :returns: The works that keep a witness, or ``None`` when none does.
    """
    text, kept = request.text, works
    while kept:
        outside = shell(text, [work.region for work in kept], [""] * len(kept))
        taken: list[str] = []
        assigned: list[RegionWork] = []
        for work in kept:
            witness = next(
                (
                    w
                    for w in witnesses(work.plan)
                    if _unique(w, outside, taken) and _keeps_edges(request, work, w)
                ),
                None,
            )
            if witness is not None:
                taken.append(witness)
                assigned.append(work._replace(witness=witness))
        if len(assigned) == len(kept):
            return assigned
        kept = [work for work in kept if any(a.region == work.region for a in assigned)]
    return None


def _keeps_edges[M](request: MergeRequest[M], work: RegionWork, witness: str) -> bool:
    """Whether :func:`_standin`'s check would pass — predicted before any piece.

    Parses the SAME stand-in text that check parses — the witness's core
    (:func:`witness_core`) inside the region's edge noise — and asks the same
    question of it: does the noise come back in the region's edge slots, or
    did the witness absorb it (a ``{}`` whose own ``ws`` takes a closing
    ``\n``, carrying it into the items the splice replaces)? The one gap: the
    exact check places the noise the PIECES' edge slots hold, and this places
    the source noise, which those slots may not hold.
    """
    text, region, plan = request.text, work.region, work.plan
    opener, closer = text[region.opener], text[region.closer]
    bare = _standin_model(request, work, opener + witness + closer)
    core = witness_core(work, bare[0], witness, text) if bare is not None else None
    if core is None:
        return False
    before = (
        _leading_noise(text, region.opener + 1, region.closer, opener, plan.outer_skip)
        if plan.outer_begin is not None
        else ""
    )
    after = (
        _trailing_noise(text, region.opener, region.closer, closer, plan.outer_trail)
        if plan.outer_end is not None
        else ""
    )
    item = before + core + after
    if item == witness:
        return True
    noisy = _standin_model(request, work, opener + item + closer)
    return noisy is not None and _edges_hold(
        plan, noisy[0], (opener, closer, before, after)
    )


def _edges_hold(plan: RegionPlan, stand: GrammarModel, edges: tuple[str, ...]) -> bool:
    """Whether a stand-in's edge slots hold exactly the noise placed at its edges.

    :param edges: The opener, the closer, and the leading and trailing noise.
    """
    opener, closer, before, after = edges
    children = stand.children()
    return (
        _edge_noise(children, plan.outer_begin, opener, True, "") == before
        and _edge_noise(children, plan.outer_end, closer, False, "") == after
    )


def _unique(witness: str, outside: str, taken: list[str]) -> bool:
    """Whether ``witness`` can occur in the shell only where it is placed."""
    if witness in outside:
        return False
    return all(witness not in other and other not in witness for other in taken)


def _edge_noise(
    children: Sequence[object],
    slot: int | None,
    boundary: str,
    opening: bool,
    fallback: str,
) -> str | None:
    """Text inside one fake boundary, or empty when that edge is inline."""
    if slot is None:
        result = ""
    elif slot >= len(children):
        result = None
    else:
        edge = children[slot]
        result = edge.to_text() if isinstance(edge, GrammarModel) else None
        if edge is None:
            result = fallback
        elif result is not None and opening and result.startswith(boundary):
            result = result[1:]
        elif result is not None and not opening and result.endswith(boundary):
            result = result[:-1]
    return result


def _leading_noise(
    text: str, start: int, stop: int, boundary: str, allowed: frozenset[str]
) -> str:
    """Return the finite wrapper prefix following an opening boundary."""
    at = start
    while at < stop and text[at] != boundary and text[at] in allowed:
        at += 1
    return text[start:at]


def _trailing_noise(
    text: str, start: int, stop: int, boundary: str, allowed: frozenset[str]
) -> str:
    """Return the finite wrapper suffix preceding a closing boundary."""
    at = stop
    while at > start and text[at - 1] != boundary and text[at - 1] in allowed:
        at -= 1
    return text[at:stop]


def witness_core(
    work: RegionWork, stand: GrammarModel, raw: str, text: str
) -> str | None:
    """A witness without the edge noise its own parse put in the region's slots.

    ``stand`` is the parse of the region's opener, ``raw`` and its closer, so
    this is known before any piece is parsed. The stand-in's edges are then
    whatever the caller places around the core.

    :returns: The core, or ``None`` when ``raw`` does not carry those edges.
    """
    opener, closer = text[work.region.opener], text[work.region.closer]
    wrapped = opener + raw + closer
    fake_before = _edge_noise(
        stand.children(),
        work.plan.outer_begin,
        opener,
        True,
        _leading_noise(wrapped, 1, len(wrapped) - 1, opener, work.plan.outer_skip),
    )
    fake_after = _edge_noise(
        stand.children(),
        work.plan.outer_end,
        closer,
        False,
        _trailing_noise(wrapped, 1, len(wrapped) - 1, closer, work.plan.outer_trail),
    )
    if fake_before is None or fake_after is None:
        return None
    if not raw.startswith(fake_before) or not raw.endswith(fake_after):
        return None
    core_end = len(raw) - len(fake_after) if fake_after else len(raw)
    if core_end < len(fake_before):
        return None
    return raw[len(fake_before) : core_end]


def _boundary_stub(
    work: RegionWork,
    models: list[GrammarModel],
    stand: GrammarModel,
    raw: str,
    text: str,
) -> tuple[str, str, str] | None:
    """Replace a stand-in's boundary noise with the delegated source noise.

    :returns: The stand-in text, and the leading and trailing noise put into it.
    """
    begin_at, end_at = work.plan.outer_begin, work.plan.outer_end
    opener, closer = text[work.region.opener], text[work.region.closer]
    source_before = _leading_noise(
        text, work.region.opener + 1, work.region.closer, opener, work.plan.outer_skip
    )
    source_after = _trailing_noise(
        text, work.region.opener, work.region.closer, closer, work.plan.outer_trail
    )
    before = _edge_noise(models[0].children(), begin_at, opener, True, source_before)
    after = _edge_noise(models[-1].children(), end_at, closer, False, source_after)
    core = witness_core(work, stand, raw, text)
    if before is None or after is None or core is None:
        return None
    return before + core + after, before, after


def _standin_model[M](
    request: MergeRequest[M], work: RegionWork, source: str
) -> tuple[GrammarModel, GrammarModel] | None:
    """Parse one bounded generated shell stand-in and locate its items node."""
    try:
        stand = request.run(work.plan.root, source)
    except LexicError:
        return None
    if not isinstance(stand, GrammarModel):
        return None
    needle = region_items(stand, work.plan)
    shaped = head_rest(needle, work.plan) if needle is not None else None
    return (stand, needle) if shaped is not None and needle is not None else None


def _standin[M](
    request: MergeRequest[M],
    work: RegionWork,
    models: list[GrammarModel],
) -> tuple[GrammarModel, str, GrammarModel] | None:
    """Merged items and the shallow shell needle standing in for them."""
    value = _merge_items(request, work, models)
    if not work.witness:
        return None
    raw = work.witness
    wrapped = request.text[work.region.opener] + raw + request.text[work.region.closer]
    parsed = _standin_model(request, work, wrapped)
    if value is None or parsed is None:
        return None
    stand, needle = parsed
    stub = _boundary_stub(work, models, stand, raw, request.text)
    if stub is None:
        return None
    item, before, after = stub
    if item != raw:
        parsed = _standin_model(request, work, wrapped[0] + item + wrapped[-1])
        # The source noise must land in the region's edge slots: absorbed by
        # the witness instead, it sits in the items the splice replaces.
        edges = (wrapped[0], wrapped[-1], before, after)
        if parsed is None or not _edges_hold(work.plan, parsed[0], edges):
            return None
        _stand, needle = parsed
    return value, item, needle


class Standins(NamedTuple):
    """All reconstructed region values and their shell stand-ins."""

    values: list[GrammarModel]
    text: list[str]
    needles: list[GrammarModel]


def standins[M](
    request: MergeRequest[M],
    works: list[RegionWork],
    parsed: list[list[GrammarModel]],
) -> Standins | None:
    """Build every region's merged value and shallow unique shell needle."""
    out = Standins([], [], [])
    needles: dict[tuple[int, str], list[GrammarModel]] = {}
    for work, models in zip(works, parsed, strict=True):
        key = (id(work.plan.root), work.plan.head_rule)
        stand = _standin(request, work, models)
        if stand is None:
            return None
        value, source, needle = stand
        if needle in needles.setdefault(key, []):
            return None
        needles[key].append(needle)
        out.values.append(value)
        out.text.append(source)
        out.needles.append(needle)
    return out


def stitch_shell[M](
    request: MergeRequest[M],
    grammar: IrAst,
    works: list[RegionWork],
    stands: Standins,
) -> M | None:
    """Parse the small enclosing shell and attach delegated region values."""
    try:
        whole = request.run(
            grammar,
            shell(request.text, [work.region for work in works], stands.text),
        )
    except LexicError:
        return None
    if not isinstance(whole, GrammarModel):
        return None
    routes = [sole_route(whole, needle) for needle in stands.needles]
    found = [route for route in routes if route is not None]
    if len(found) != len(routes):
        return None
    for route, value in zip(found, stands.values, strict=True):
        spliced = splice(whole, route, value)
        if spliced is None:
            return None
        whole = spliced
    return whole
