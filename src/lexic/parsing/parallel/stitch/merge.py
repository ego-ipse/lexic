"""Rebuild delegated region models and attach them to a small parsed shell.

The expensive recursive heads belong to piece workers.  Boundary tails reuse
an already parsed separator shape when that shape spells exactly the certified
separator, and the enclosing shell uses a grammar-generated shallow head.
Neither path reparses a delegated subtree merely to discover where it belongs.
"""

from __future__ import annotations

import random
from bisect import bisect_left
from collections.abc import Callable
from typing import Any, NamedTuple, cast

from lexic.exceptions import LexicError
from lexic.generate import generate
from lexic.ir import IrAst
from lexic.model import GrammarModel
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.fold import ModelFold
from lexic.parsing.parallel.discovery.regions import shell, stub
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


def _source_tail[M](
    request: MergeRequest[M],
    work: RegionWork,
    cut: int,
) -> GrammarModel | None:
    """Reparse one boundary when no exact separator template is available."""
    marks = work.region.marks
    at = bisect_left(marks, cut)
    if at == len(marks) or marks[at] != cut:
        return None
    lo = work.region.opener + 1 if at == 0 else marks[at - 1] + 1
    hi = work.region.closer if at + 1 == len(marks) else marks[at + 1]
    text = request.text
    wrapped = text[work.region.opener] + text[lo:hi] + text[work.region.closer]
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
    tail = shaped[1][0]
    return tail if tail.__class__ is work.plan.tail_type else None


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


def _boundary_lead(work: RegionWork, later: GrammarModel, text: str) -> str | None:
    """The cut separator plus noise owned by the later piece's fake opener."""
    lead = work.plan.separator
    begin_at = work.plan.outer_begin
    if begin_at is None:
        return lead
    children = later.children()
    if begin_at >= len(children):
        return None
    begin = children[begin_at]
    if not isinstance(begin, GrammarModel):
        return None
    before = begin.to_text()
    opener = text[work.region.opener]
    return lead + before[1:] if before.startswith(opener) else None


def _shallow_tail[M](
    request: MergeRequest[M],
    work: RegionWork,
    later: GrammarModel,
    head: GrammarModel,
) -> GrammarModel | None:
    """Parse only a shallow boundary witness, then attach the delegated head."""
    witness = _witness(work.plan, 0)
    lead = _boundary_lead(work, later, request.text)
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


def _joint_tail[M](
    request: MergeRequest[M],
    work: RegionWork,
    cut: int,
    later: GrammarModel,
    head: GrammarModel,
) -> GrammarModel | None:
    """Prefer a shallow boundary witness, with exact source fallback."""
    shallow = _shallow_tail(request, work, later, head)
    return shallow if shallow is not None else _source_tail(request, work, cut)


def _joined_tails[M](
    request: MergeRequest[M],
    work: RegionWork,
    models: list[GrammarModel],
    shaped: list[tuple[GrammarModel, tuple[GrammarModel, ...]]],
) -> list[GrammarModel] | None:
    """Join existing tails with each removed separator boundary."""
    merged = list(shaped[0][1])
    later_parts = zip(models[1:], shaped[1:], strict=True)
    for cut, (later, (head, rest)) in zip(work.cuts, later_parts, strict=True):
        tail = _joint_tail(request, work, cut, later, head)
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


_WITNESSES: dict[tuple[int, str, int], tuple[IrAst, str | None]] = {}
"""Stable shallow head text per rooted grammar, with identity pinned."""


def _witness(plan: RegionPlan, index: int) -> str | None:
    """Generate one minimal-depth head for the shell, or decline to source."""
    key = (id(plan.root), plan.head_rule, index)
    entry = _WITNESSES.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in plan.root.rules}
        try:
            value = generate(
                plan.head_rule,
                rules,
                rng=random.Random(index),
                max_depth=0,
            )
        except LexicError:
            value = None
        entry = (plan.root, value)
        _WITNESSES[key] = entry
    return entry[1]


def _boundary_stub(
    work: RegionWork,
    models: list[GrammarModel],
    raw: str,
    wrapped: str,
    head: GrammarModel,
) -> str | None:
    """Restore boundary-owned whitespace around one stand-in."""
    begin_at, end_at = work.plan.outer_begin, work.plan.outer_end
    if begin_at is None or end_at is None:
        return raw
    first, last = models[0].children(), models[-1].children()
    if begin_at >= len(first) or end_at >= len(last):
        return None
    begin, end = first[begin_at], last[end_at]
    if not isinstance(begin, GrammarModel) or not isinstance(end, GrammarModel):
        return raw
    before, after = begin.to_text(), end.to_text()
    if not before.startswith(wrapped[0]) or not after.endswith(wrapped[-1]):
        return None
    return before[1:] + head.to_text() + after[:-1]


def _standin[M](
    request: MergeRequest[M],
    work: RegionWork,
    models: list[GrammarModel],
    index: int,
    shallow: bool,
) -> tuple[GrammarModel, str, GrammarModel] | None:
    """Merged items and the shallow shell needle standing in for them."""
    value = _merge_items(request, work, models)
    generated = _witness(work.plan, index) if shallow else None
    text = request.text
    raw = generated if generated is not None else stub(text, work.region, index)
    wrapped = text[work.region.opener] + raw + text[work.region.closer]
    try:
        stand = request.run(work.plan.root, wrapped)
    except LexicError:
        return None
    if value is None or not isinstance(stand, GrammarModel):
        return None
    needle = region_items(stand, work.plan)
    shaped = head_rest(needle, work.plan) if needle is not None else None
    if shaped is None:
        return None
    item = _boundary_stub(work, models, raw, wrapped, shaped[0])
    if item is None:
        return None
    if item != raw:
        try:
            stand = request.run(work.plan.root, wrapped[0] + item + wrapped[-1])
        except LexicError:
            return None
        needle = (
            region_items(stand, work.plan) if isinstance(stand, GrammarModel) else None
        )
    return (value, item, needle) if needle is not None else None


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
    for work in works:
        key = (id(work.plan.root), work.plan.head_rule)
        counts[key] = counts.get(key, 0) + 1
    for index, (work, models) in enumerate(zip(works, parsed, strict=True)):
        key = (id(work.plan.root), work.plan.head_rule)
        stand = _standin(
            request,
            work,
            models,
            index,
            counts[key] == 1,
        )
        if stand is None:
            return None
        value, source, needle = stand
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
