"""Stitching a routed interior — concatenation, then one splice.

A region the character sweep finds holds SEPARATED items, so putting it back
together means rebuilding every separator the cuts consumed. A routed interior
holds a terminated repetition instead: each unit owns its final character, so
the pieces' runs concatenate untouched and the only work left is putting that
run back where it came from.

The enclosing document is parsed once with a single-unit stand-in interior —
small, and shaped exactly like the real one — and the stand-in's run is
replaced by the concatenation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from lexic.exceptions import LexicError
from lexic.ir import IrAst, IrNamedTuple, IrSelf
from lexic.model import GrammarModel
from lexic.parsing.fold import ModelFold
from lexic.parsing.products import ModelBinding
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.plan.routed import (
    RoutedPlan,
    divide,
    locate,
    routed_plan,
)
from lexic.parsing.parallel.pool import WorkPool
from lexic.parsing.parallel.replicas import worker_replicas
from lexic.parsing.parallel.stitch.model import field_slot, splice


def interior_route[M: IrNamedTuple](
    fold: ModelFold[M], container: str, at: int, rule: str, run: int
) -> tuple[int, int] | None:
    """``(slot of the interior, slot of its run)``, or ``None``.

    :param container: The rule whose arm carries the optional interior.
    :param at: That interior's item index in the arm.
    :param rule: The interior's own rule.
    :param run: The repetition's item index within it.
    """
    outer = fold.config.get(container)
    inner = fold.config.get(rule)
    if outer is None or inner is None:
        return None
    slot = field_slot(outer, at)
    child = field_slot(inner, run)
    return None if slot is None or child is None else (slot, child)


def stitch_interior(
    shell: GrammarModel, pieces: list[GrammarModel], route: tuple[int, int]
) -> GrammarModel | None:
    """Put the pieces' runs back into the shell; ``None`` = shape surprise."""
    slot, child = route
    fields = list(shell.children())
    stand = fields[slot] if slot < len(fields) else None
    if not isinstance(stand, GrammarModel):
        return None
    merged = _merged_run(pieces, child)
    if merged is None:
        return None
    rebuilt = list(stand.children())
    rebuilt[child] = cast(IrSelf, merged)
    return splice(shell, ((slot, None),), stand.rebuild(rebuilt))


def _merged_run(pieces: list[GrammarModel], child: int) -> tuple | None:
    """Every piece's repeated run, end to end, or ``None`` on a shape miss."""
    merged: list[IrSelf] = []
    for piece in pieces:
        run = list(piece.children())
        if child >= len(run) or run[child].__class__ is not tuple:
            return None
        merged.extend(cast(tuple, run[child]))
    return tuple(merged)


def routed_split[M: IrNamedTuple](
    parse: Callable[..., Any],
    grammar: IrAst,
    ask: tuple[str, ModelBinding[M], object],
    pool: WorkPool,
) -> M | None:
    """Split a routed interior across the pool, or ``None`` for sequential.

    The interior's pieces are the only concurrent work: the enclosing document
    is one small parse of a stand-in shell, and putting them back is a
    concatenation. Anything unproven — no route, no balanced division, a piece
    that will not parse — declines to the caller's sequential parse.
    """
    text, binding, resolve = ask
    plan = routed_plan(grammar)
    region = locate(text, plan) if plan is not None else None
    parts = divide(text, region, pool.workers) if region is not None else None
    if plan is None or region is None or parts is None:
        return None
    route = interior_route(
        binding.fold, str(grammar.start), plan.at, plan.rule, plan.run
    )
    if route is None:
        return None
    parsed = _parsed(
        parse, grammar, (text, binding, resolve), (plan, region, parts), pool
    )
    if parsed is None:
        return None
    shell, pieces = parsed
    return cast(M, stitch_interior(shell, pieces, route))


def _parsed(
    parse: Callable[..., Any],
    grammar: IrAst,
    ask: tuple[str, ModelBinding, object],
    work: tuple[RoutedPlan, Region, list[str]],
    pool: WorkPool,
) -> tuple[GrammarModel, list[GrammarModel]] | None:
    """Parse the stand-in shell and every piece, or decline."""
    text, binding, resolve = ask
    plan, region, parts = work
    views = worker_replicas(plan.rooted, binding, len(parts))
    try:
        shell = parse(grammar, _stand_in(text, region), binding, resolve)
        pieces = pool.map(
            lambda k: parse(views[k][0], parts[k], views[k][1], resolve),
            list(range(len(parts))),
        )
    except LexicError:
        return None
    whole = isinstance(shell, GrammarModel) and all(
        isinstance(piece, GrammarModel) for piece in pieces
    )
    return (shell, pieces) if whole else None


def _stand_in(text: str, region: Region) -> str:
    """The document with the interior reduced to its first unit."""
    keep = text[region.opener + 1 : region.marks[0] + 1]
    return text[: region.opener + 1] + keep + text[region.closer :]
