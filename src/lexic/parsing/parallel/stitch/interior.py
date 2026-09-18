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
    INTO_UNIT,
    Descent,
    RoutedPlan,
    divide,
    locate,
    routed_plan,
)
from lexic.parsing.parallel.pool import WorkPool
from lexic.parsing.parallel.replicas import worker_parse
from lexic.parsing.parallel.stitch.model import ModelStep, is_run, splice
from lexic.parsing.parallel.stitch.plan import field_slot


def interior_route[M: IrNamedTuple](
    binding: ModelExecutable[M],
    chain: tuple[Descent, ...],
    rule: str,
    run: int,
    whole: bool,
) -> tuple[tuple[ModelStep, ...], int] | None:
    """``(the steps down to the interior, the slot of its run)``, or ``None``.

    One step per :class:`Descent`, so the route says exactly as much as the
    descent did. A route reaching the wrong node cannot be built: the only
    thing deciding the depth is the chain, and the chain is what the descent
    recorded while walking. The two-integer form it replaces derived the
    interior's depth and its run's index independently, and they could
    disagree.

    A step addresses an element of a RUN when it descends into a repeated unit
    (:data:`INTO_UNIT`), or when it is the last step of a whole-extent
    interior — which sits inside its enclosing repetition rather than in a
    field of its own.

    :param chain: The descent from the start rule to the interior's rule.
    :param rule: The interior's own rule.
    :param run: The repetition's item index within it.
    :param whole: Whether the interior is its enclosing node's whole extent.
    """
    steps: list[ModelStep] = []
    for index, step in enumerate(chain):
        routine = binding.routines.get(step.rule)
        slot = field_slot(routine, step.item) if routine is not None else None
        if slot is None:
            return None
        last = index == len(chain) - 1
        in_run = step.kind == INTO_UNIT or (last and whole)
        steps.append((slot, 0 if in_run else None))
    inner = binding.routines.get(rule)
    child = field_slot(inner, run) if inner is not None else None
    return None if child is None else (tuple(steps), child)


def _walk_down(node: object, steps: tuple[ModelStep, ...]) -> GrammarModel | None:
    """The model the steps address, or ``None`` when the shape surprises.

    A slot the model does not have is a chain/model disagreement and RAISES; a
    run holding the wrong number of elements is a document shape and declines.

    **The arity guard lives here.** ``splice`` bounds a run index
    (``repeated >= len(child)``) but never checks arity, so a step naming
    element 0 of a run of three succeeds and rewrites the first, leaving the
    other two where they are — a wrong model rather than a refusal. The
    exactly-one check that used to sit in the two-slot caller was written about
    a PIECE, where one unit is true by construction; an intermediate step runs
    over the WHOLE model, where it is not.

    So every run step is required to hold exactly one element, and a run of two
    declines the plan here rather than being silently indexed.
    """
    current: object = node
    for slot, index in steps:
        if not isinstance(current, GrammarModel):
            return None
        fields = list(current.children())
        if slot >= len(fields):
            # Provisional pending item 2 (the engine-invariant exception).
            # The chain's slots come from the binding's own routines, so a
            # slot the model does not have means the chain and the model
            # disagree about the grammar — not a document shape. `LexicError`
            # is caught by the split seam and would fall back to a correct
            # sequential parse, hiding it.
            raise RuntimeError(
                f"routed chain names slot {slot} of "
                f"{type(current).__name__}, which has {len(fields)}"
            )
        held = fields[slot]
        if index is None:
            current = held
            continue
        if not is_run(held) or len(held) != 1:
            return None  # a run of two was never one run; the plan declines
        current = held[0]
    return current if isinstance(current, GrammarModel) else None


def stitch_interior[S: GrammarModel](
    shell: S,
    pieces: list[GrammarModel],
    route: tuple[tuple[ModelStep, ...], int],
    whole: bool = False,
) -> S | None:
    """Put the pieces' runs back into the shell; ``None`` = shape surprise."""
    steps, child = route
    stand = _walk_down(shell, steps)
    if stand is None:
        return None
    merged = (
        _merged_whole(pieces, steps, child) if whole else _merged_run(pieces, child)
    )
    if merged is None:
        return None
    rebuilt: list[Bound] = list(stand.children())
    rebuilt[child] = merged
    return splice(shell, steps, stand.rebuild(rebuilt))


def _merged_whole(
    pieces: list[GrammarModel], steps: tuple[ModelStep, ...], child: int
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
        node = _walk_down(piece, steps)
        if node is None:
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
    route = interior_route(binding, plan.chain, plan.rule, plan.run, plan.whole)
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
