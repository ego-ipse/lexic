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

from lexic.exceptions import LexicError
from lexic.ir import Bound, IrAst, IrNamedTuple, IrSelf
from lexic.model import GrammarModel
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.plan.routed import (
    RoutedPlan,
    divide,
    locate,
    routed_plan,
)
from lexic.parsing.parallel.pool import WorkPool
from lexic.parsing.parallel.replicas import worker_parse
from lexic.parsing.parallel.stitch.model import is_run, splice
from lexic.parsing.parallel.stitch.plan import field_slot


def interior_route[M: IrNamedTuple](
    binding: ModelExecutable[M], container: str, at: int, rule: str, run: int
) -> tuple[int, int] | None:
    """``(slot of the interior, slot of its run)``, or ``None``.

    :param container: The rule whose arm carries the optional interior.
    :param at: That interior's item index in the arm.
    :param rule: The interior's own rule.
    :param run: The repetition's item index within it.
    """
    outer = binding.routines.get(container)
    inner = binding.routines.get(rule)
    if outer is None or inner is None:
        return None
    slot = field_slot(outer, at)
    child = field_slot(inner, run)
    return None if slot is None or child is None else (slot, child)


def stitch_interior[S: GrammarModel](
    shell: S, pieces: list[GrammarModel], route: tuple[int, int], whole: bool = False
) -> S | None:
    """Put the pieces' runs back into the shell; ``None`` = shape surprise."""
    slot, child = route
    fields = list(shell.children())
    held = fields[slot] if slot < len(fields) else None
    # A whole-extent interior is a member of its enclosing RUN, not a field of
    # its own: `root ::= para*` holds the stand-in para inside the repetition,
    # where a delimited interior sits in a field. The route's step says which,
    # and `splice` has always taken both.
    stand = held[0] if whole and is_run(held) and len(held) == 1 else held
    if not isinstance(stand, GrammarModel):
        return None
    merged = _merged_whole(pieces, slot, child) if whole else _merged_run(pieces, child)
    if merged is None:
        return None
    rebuilt: list[Bound] = list(stand.children())
    rebuilt[child] = merged
    step = (slot, 0) if whole else (slot, None)
    return splice(shell, (step,), stand.rebuild(rebuilt))


def _merged_whole(
    pieces: list[GrammarModel], slot: int, child: int
) -> tuple[IrSelf, ...] | None:
    """Every piece's run when the piece is a whole START document.

    A whole-extent interior's piece parses under the start rule rather than
    under the interior's own rule, because that is what the predictive engine
    settles. So its run sits one level deeper than a delimited piece's: the
    start model's repetition holds exactly ONE element — the piece is one unit
    by construction — and the run is inside that.

    A piece holding more than one is a shape surprise and declines, because the
    concatenation would then be joining runs that were never one run.
    """
    merged: list[IrSelf] = []
    for piece in pieces:
        outer = list(piece.children())
        held = outer[slot] if slot < len(outer) else None
        if not is_run(held) or len(held) != 1:
            return None
        node = held[0]
        if not isinstance(node, GrammarModel):
            return None
        inner = list(node.children())
        found = inner[child] if child < len(inner) else None
        if not is_run(found):
            return None
        merged.extend(found)
    return tuple(merged)


def _merged_run(pieces: list[GrammarModel], child: int) -> tuple[IrSelf, ...] | None:
    """Every piece's repeated run, end to end, or ``None`` on a shape miss."""
    merged: list[IrSelf] = []
    for piece in pieces:
        run = list(piece.children())
        found = run[child] if child < len(run) else None
        if not is_run(found):
            return None
        merged.extend(found)
    return tuple(merged)


def routed_split[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: tuple[str, ModelExecutable[M], Resolver | None],
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
    if plan is None:
        return None
    region = locate(text, plan)
    parts = divide(text, region, pool.workers, plan) if region is not None else None
    if region is None or parts is None:
        return None
    route = interior_route(binding, str(grammar.start), plan.at, plan.rule, plan.run)
    if route is None:
        return None
    parsed = _parsed(
        parse, grammar, (text, binding, resolve), (plan, region, parts), pool
    )
    if parsed is None:
        return None
    shell, pieces = parsed
    if not isinstance(shell, GrammarModel):
        return None
    return stitch_interior(shell, pieces, route, plan.whole)


def _parsed[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: tuple[str, ModelExecutable[M], Resolver | None],
    work: tuple[RoutedPlan, Region, list[str]],
    pool: WorkPool,
) -> tuple[M, list[GrammarModel]] | None:
    """Parse the stand-in shell and every piece, or decline.

    The shell keeps the product's own type; whether it is a model at all is
    the caller's question, asked where the answer is needed.
    """
    text, binding, resolve = ask
    plan, region, parts = work
    try:
        shell = parse(grammar, _stand_in(text, region), binding, resolve)
        pieces = pool.map(
            lambda k: worker_parse(parse, plan.rooted, parts[k], binding, resolve),
            list(range(len(parts))),
        )
    except LexicError:
        return None
    models = [piece for piece in pieces if isinstance(piece, GrammarModel)]
    if len(models) != len(pieces):
        return None
    return shell, models


def _stand_in(text: str, region: Region) -> str:
    """The document with the interior reduced to its first unit."""
    keep = text[region.opener + 1 : region.marks[0] + 1]
    return text[: region.opener + 1] + keep + text[region.closer :]
