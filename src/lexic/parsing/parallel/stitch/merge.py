"""Rebuild delegated region models and attach them to a small parsed shell.

The expensive recursive heads belong to piece workers.  Boundary tails reuse
an already parsed separator shape when that shape spells exactly the certified
separator, and the enclosing shell uses a grammar-generated shallow head.
Neither path reparses a delegated subtree merely to discover where it belongs.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import Any, NamedTuple, cast

from lexic.exceptions import LexicError
from lexic.generate import generate
from lexic.ir import IrAst
from lexic.model import GrammarModel
from lexic.parsing.caches import memo
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.fold import ModelFold
from lexic.parsing.parallel.discovery.regions import shell
from lexic.parsing.parallel.stitch.model import (
    RegionPlan,
    RegionWork,
    head_rest,
    region_items,
    sole_route,
    splice,
)

ModelProduct = Callable[..., Any]


class MergeRequest[M](NamedTuple):
    """The parse service and per-document inputs shared by every stitch step."""

    parse: ModelProduct
    text: str
    fold: ModelFold[M]
    resolve: Resolver | None

    def run(self, grammar: IrAst, text: str) -> Any:
        """Parse one full, piece, boundary, or shell document."""
        return self.parse(grammar, text, self.fold, self.resolve)


def _replace_tail_head(
    template: GrammarModel, head: GrammarModel, plan: RegionPlan
) -> GrammarModel | None:
    """Reuse a certified one-character separator around a delegated head."""
    children = cast(list[Any], list(template.children()))
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
    children = cast(list[Any], list(first_items.children()))
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


_WITNESSES: dict[tuple[int, str, int], tuple[IrAst, str | None]] = memo({}, 0)
"""Stable shallow head text per rooted grammar, with identity pinned."""


def _witness(plan: RegionPlan, index: int) -> str | None:
    """Generate the indexed distinct bounded head, or decline the split."""
    key = (id(plan.root), plan.head_rule, index)
    entry = _WITNESSES.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in plan.root.rules}
        values: list[str] = []
        value: str | None = None
        for depth in range(3):
            for seed in range(64):
                try:
                    candidate = generate(
                        plan.head_rule,
                        rules,
                        rng=random.Random(seed),
                        max_depth=depth,
                    )
                except LexicError:
                    continue
                if len(candidate) > 256 or candidate in values:
                    continue
                if len(values) == index:
                    value = candidate
                    break
                values.append(candidate)
            if value is not None:
                break
        entry = (plan.root, value)
        _WITNESSES[key] = entry
    return entry[1]


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


def _boundary_stub(
    work: RegionWork,
    models: list[GrammarModel],
    stand: GrammarModel,
    raw: str,
    text: str,
) -> str | None:
    """Replace a stand-in's boundary noise with the delegated source noise."""
    begin_at, end_at = work.plan.outer_begin, work.plan.outer_end
    if begin_at is None and end_at is None:
        return raw
    wrapped = text[work.region.opener] + raw + text[work.region.closer]
    source_before = _leading_noise(
        text,
        work.region.opener + 1,
        work.region.closer,
        wrapped[0],
        work.plan.outer_skip,
    )
    source_after = _trailing_noise(
        text,
        work.region.opener,
        work.region.closer,
        wrapped[-1],
        work.plan.outer_trail,
    )
    before = _edge_noise(
        models[0].children(),
        begin_at,
        wrapped[0],
        True,
        source_before,
    )
    after = _edge_noise(
        models[-1].children(),
        end_at,
        wrapped[-1],
        False,
        source_after,
    )
    if before is None or after is None:
        return None
    fake_before = _edge_noise(
        stand.children(),
        begin_at,
        wrapped[0],
        True,
        _leading_noise(wrapped, 1, len(wrapped) - 1, wrapped[0], work.plan.outer_skip),
    )
    fake_after = _edge_noise(
        stand.children(),
        end_at,
        wrapped[-1],
        False,
        _trailing_noise(
            wrapped, 1, len(wrapped) - 1, wrapped[-1], work.plan.outer_trail
        ),
    )
    if fake_before is None or fake_after is None:
        return None
    if not raw.startswith(fake_before) or not raw.endswith(fake_after):
        return None
    core_end = len(raw) - len(fake_after) if fake_after else len(raw)
    if core_end < len(fake_before):
        return None
    return before + raw[len(fake_before) : core_end] + after


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
    index: int,
) -> tuple[GrammarModel, str, GrammarModel] | None:
    """Merged items and the shallow shell needle standing in for them."""
    value = _merge_items(request, work, models)
    generated = _witness(work.plan, index)
    if generated is None:
        return None
    text = request.text
    raw = generated
    wrapped = text[work.region.opener] + raw + text[work.region.closer]
    parsed = _standin_model(request, work, wrapped)
    if value is None or parsed is None:
        return None
    stand, needle = parsed
    item = _boundary_stub(work, models, stand, raw, request.text)
    if item is None:
        return None
    if item != raw:
        parsed = _standin_model(request, work, wrapped[0] + item + wrapped[-1])
        if parsed is None:
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
    counts: dict[tuple[int, str], int] = {}
    needles: dict[tuple[int, str], list[GrammarModel]] = {}
    for work, models in zip(works, parsed, strict=True):
        key = (id(work.plan.root), work.plan.head_rule)
        index = counts.get(key, 0)
        stand = _standin(request, work, models, index)
        if stand is None:
            return None
        value, source, needle = stand
        if needle in needles.setdefault(key, []):
            return None
        counts[key] = index + 1
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
    if any(route is None for route in routes):
        return None
    for route, value in zip(routes, stands.values, strict=True):
        whole = splice(whole, cast(tuple, route), value)
        if whole is None:
            return None
    return cast(M, whole)
