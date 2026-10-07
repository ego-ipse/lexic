"""Stitching a routed interior — concatenation, then one splice.

A region the character sweep finds holds SEPARATED items, so putting it back
together means rebuilding every separator the cuts consumed. A routed interior
holds a terminated repetition instead: each unit owns its final character, so
the pieces' runs concatenate untouched and the only work left is putting that
run back where it came from.

The enclosing document is parsed once with a single-unit stand-in interior —
small, and shaped exactly like the real one — and the stand-in's run is
replaced by the concatenation.

A FOLDED spine is the third source's stitch, and it is the same left fold with
a different seed and step: ``reduce(concatenate, pieces, ())`` becomes a reduce
whose seed is the first piece's spine and whose step grafts the accumulated
value onto the next piece's innermost base. It shares this module because it
shares the shape — locate, divide, parse, reconstruct through the binding —
and differs only in what the join builds.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from lexic.exceptions import EngineInvariantError, LexicError
from lexic.ir import Bound, IrAst, IrNamedTuple, IrSelf
from lexic.model import GrammarModel
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.plan.folded import FoldedPlan, Pieces
from lexic.parsing.parallel.plan.folded import divide as folded_divide
from lexic.parsing.parallel.plan.folded import folded_plan
from lexic.parsing.parallel.plan.folded import locate as folded_locate
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
from lexic.parsing.parallel.stitch.plan import field_slot, model_type

type Ask[M] = tuple[str, ModelExecutable[M], ParseConfig]
"""One document's split request, as the orchestrator hands it down: the text,
its bound product and the caller's configuration."""


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
            # The chain's slots come from the binding's own routines, so a
            # slot the model does not have means the chain and the model
            # disagree about the grammar — not a document shape.
            raise EngineInvariantError(
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
    ask: Ask[M],
    pool: WorkPool,
) -> M | None:
    """Split a routed interior across the pool, or ``None`` for sequential.

    The interior's pieces are the only concurrent work: the enclosing document
    is one small parse of a stand-in shell, and putting them back is a
    concatenation. Anything unproven — no route, no balanced division, a piece
    that will not parse — declines to the caller's sequential parse.
    """
    text, binding, *_ = ask
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
    parsed = _parsed(parse, grammar, ask, (plan, region, parts), pool)
    if parsed is None:
        return None
    shell, pieces = parsed
    if not isinstance(shell, GrammarModel):
        return None
    return stitch_interior(shell, pieces, route, plan.whole)


def _parsed[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Ask[M],
    work: tuple[RoutedPlan, Region, list[str]],
    pool: WorkPool,
) -> tuple[M, list[GrammarModel]] | None:
    """Parse the stand-in shell and every piece, or decline.

    The shell keeps the product's own type; whether it is a model at all is
    the caller's question, asked where the answer is needed.
    """
    text, binding, config = ask
    plan, region, parts = work
    try:
        shell = parse(grammar, _stand_in(text, region), binding, config)
        pieces = pool.map(
            lambda k: worker_parse(parse, plan.rooted, parts[k], binding, config),
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


def fold_route[M: IrNamedTuple](
    binding: ModelExecutable[M], chain: tuple[Descent, ...]
) -> tuple[ModelStep, ...] | None:
    """The model route from a piece's root down to the folded rule's node.

    Every step is a single-occurrence reference, so no step addresses a run —
    which is what tells this route apart from a routed interior's, where the
    last step reaches an element of a repetition.
    """
    steps: list[ModelStep] = []
    for step in chain:
        routine = binding.routines.get(step.rule)
        slot = field_slot(routine, step.item) if routine is not None else None
        if slot is None:
            return None
        steps.append((slot, None))
    return tuple(steps)


def _left_edge(
    node: GrammarModel, step: type[GrammarModel], at: int
) -> tuple[list[GrammarModel], GrammarModel]:
    """One spine's step nodes, outermost first, and the base beneath them.

    Iterative because the spine is as deep as its piece: the recursive reading
    of this walk raises on exactly the models it exists to measure.

    The descent reads ``node[at]`` rather than ``children()[0]``. A record IS
    its field tuple on this spine, so the field index is a C-level index,
    where ``children`` builds a list per node — which is the whole cost of a
    walk that otherwise does nothing.
    """
    spine: list[GrammarModel] = []
    while node.__class__ is step:
        spine.append(node)
        below = node[at]
        if not isinstance(below, GrammarModel):
            return spine, node
        node = below
    return spine, node


def left_slot(step: type[GrammarModel]) -> int:
    """Which FIELD of a step node holds the value it recurses into.

    The recursive item leads the arm, so it is the first BOUND field — and
    what the licence below wants is that field's index among all of them,
    which a class with an unbound field would put elsewhere.
    """
    bound = sorted(step.bound_fields().items())
    return step._fields.index(bound[0][1][0]) if bound else -1


def fold_spines(
    spines: list[GrammarModel],
    leads: tuple[GrammarModel, ...],
    step: type[GrammarModel],
) -> GrammarModel | None:
    """The pieces' spines as one, left-associated; ``None`` = shape surprise.

    The same left fold the concatenating stitch runs, with a different seed
    and a different step: the seed is the first piece's spine, and each join
    grafts the accumulated value onto the NEXT piece's innermost base through
    the removed mark — which the cut consumed and only the join can rebuild.

    The accumulator is never re-walked. Each piece's left edge is walked once
    and rebuilt from the graft upwards, so the whole stitch costs one
    construction per iteration the cuts separated, rather than one per
    iteration per join.

    **Those constructions go through the class's own positional licence**, the
    one the parse builds every node of this spine with. ``rebuild`` derives
    the bound-field map per call and then pays the checked constructor, which
    measured 11 us a node against a 5.8 ms whole parse — the stitch alone cost
    more than half of what it was dividing.
    """
    at = left_slot(step)
    if at < 0 or len(leads) != len(spines) - 1:
        return None
    edges = [_left_edge(spine, step, at) for spine in spines]
    template = next((nodes[-1] for nodes, _base in edges if nodes), None)
    if template is None:
        return None
    construct, _defaults, _fields = step.fast_construct()
    joined = edges[0][0][0] if edges[0][0] else edges[0][1]
    for index in range(1, len(spines)):
        nodes, base = edges[index]
        graft = template.rebuild([joined, leads[index - 1], base])
        joined = _regraft(nodes, at, construct, graft)
    return joined


def _regraft(
    nodes: list[GrammarModel],
    at: int,
    construct: Callable[[list[Any]], GrammarModel],
    value: GrammarModel,
) -> GrammarModel:
    """Rebuild one piece's left edge above a grafted value, innermost first.

    A record IS its field tuple here, so each level is one list copy with one
    slot replaced and one positional construction — no field map, no
    validation, and no walk of what was already built.
    """
    for node in reversed(nodes):
        values = list(node)
        values[at] = value
        value = construct(values)
    return value


def folded_split[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Ask[M],
    pool: WorkPool,
) -> M | None:
    """Split a folded left recursion across the pool, or ``None`` = sequential.

    Every piece is a whole document — it re-wears the shell the source held
    out — so the concurrent work is the spine and nothing else, and what comes
    back is stitched through the step rule's own generated class.
    """
    text, binding, *_ = ask
    plan = folded_plan(grammar)
    if plan is None:
        return None
    region = folded_locate(text, plan)
    pieces = (
        folded_divide(text, region, pool.workers, plan) if region is not None else None
    )
    route = fold_route(binding, plan.chain)
    step = model_type(binding.routines.get(plan.step))
    if pieces is None or route is None or step is None:
        return None
    parsed = _folded_models(parse, grammar, ask, (plan, pieces), pool)
    if parsed is None:
        return None
    return _folded_stitch(parsed, route, step)


def _folded_stitch[M: IrNamedTuple](
    parsed: tuple[list[M], tuple[GrammarModel, ...]],
    route: tuple[ModelStep, ...],
    step: type[GrammarModel],
) -> M | None:
    """Fold the pieces' spines and put the result back in the first shell.

    The guard is the PLAN's, and agreement is by IDENTITY: the class the plan
    names for the step rule must be the class the pieces' spine nodes are. A
    plan and a model that disagree decline here rather than building a model
    out of whichever fields happened to line up.
    """
    roots, leads = parsed
    spines = [_walk_down(root, route) for root in roots]
    if any(spine is None for spine in spines):
        return None
    found = cast(list[GrammarModel], spines)
    if not any(node.__class__ is step for node in found):
        return None
    merged = fold_spines(found, leads, step)
    if merged is None:
        return None
    rebuilt = splice(cast(GrammarModel, roots[0]), route, merged)
    return cast(M, rebuilt) if rebuilt is not None else None


def _folded_models[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Ask[M],
    work: tuple[FoldedPlan, Pieces],
    pool: WorkPool,
) -> tuple[list[M], tuple[GrammarModel, ...]] | None:
    """Every piece's document model and every removed mark's, or decline."""
    _text, binding, config = ask
    plan, pieces = work
    try:
        parts = pool.map(
            lambda k: worker_parse(parse, grammar, pieces.parts[k], binding, config),
            list(range(len(pieces.parts))),
        )
        leads = [
            parse(plan.lead_grammar, mark, binding, config) for mark in pieces.leads
        ]
    except LexicError:
        return None
    if any(not isinstance(one, GrammarModel) for one in (*parts, *leads)):
        return None
    return list(parts), tuple(cast(list[GrammarModel], leads))


SOURCES = (routed_split, folded_split)
"""The region sources, in the order a split asks them.

A source LOCATES a region the plan cascade cannot describe and splits it. The
routed one reads the start rule's route to an interior; the folded one reads
the fold's shape analysis to a spine. The order is the ordinary preference —
shapes the grammar STATES before one it only implies — and not a fitness test:
a source that declines declines for a stated reason, and the next is asked.
"""


def source_split[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Ask[M],
    pool: WorkPool,
) -> M | None:
    """The first source that takes this document, or ``None`` for sequential."""
    for source in SOURCES:
        found = source(parse, grammar, ask, pool)
        if found is not None:
            return found
    return None
