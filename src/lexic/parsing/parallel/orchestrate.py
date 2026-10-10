"""One-document model splitting and exact immutable stitching.

Start-rule repetitions and nested bracketed regions share this one entry.
Delegated interiors are removed from the enclosing shell before it parses;
non-overlapping ownership prevents parent and child workers duplicating work.
Every unsupported shape or failed piece declines to the caller's sequential
parse, so worker count never changes what an input means.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NamedTuple

from lexic.exceptions import LexicError
from lexic.ir import (
    IrAst,
    IrNamedTuple,
)
from lexic.model import GrammarModel
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    DEFAULT_CONFIG,
    ParseConfig,
)
from lexic.parsing.earley.kernel.tables.decider import LeftmostLongest
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.discovery.partition import Division, Unit, partition, units
from lexic.parsing.parallel.discovery.regions import par_find
from lexic.parsing.parallel.plan.cuts import (
    Cuts,
    cut_offsets,
    cut_spans,
    reads_a_sweep,
    rebase,
    shared_scanner,
)
from lexic.parsing.parallel.plan.envelope import (
    unit_witness,
)
from lexic.parsing.parallel.plan.split import SplitPlan
from lexic.parsing.parallel.planner import safe_plans, split_plans
from lexic.parsing.parallel.policy import (
    AUTO,
    MIN_CHUNK,
    available_workers,
    capacity,
    clears_floor,
    doc_workers,
)
from lexic.parsing.parallel.pool import PoolLease, WorkPool
from lexic.parsing.parallel.replicas import (
    settle_first_meetings,
    warm_due,
    worker_parse,
)
from lexic.parsing.parallel.stitch.interior import source_split
from lexic.parsing.parallel.stitch.merge import (
    MergeRequest,
    assign_witnesses,
    stitch_units,
)
from lexic.parsing.parallel.stitch.model import (
    envelope_tails,
    stitch_envelope,
    stitch_routed,
    stitch_terminated,
)
from lexic.parsing.parallel.stitch.plan import RegionWork
from lexic.parsing.parallel.stitch.tasks import bound_works


class Request[M: IrNamedTuple](NamedTuple):
    """One split parse's per-call inputs — what changes between documents.

    Bundled because the plan, the product and the request are three
    different lifetimes: the product is fixed, the plan is per grammar, and
    only this varies per call.

    :ivar text: The document.
    :ivar binding: The bound model product producing ``M``.
    :ivar config: The caller's resolver and split decider.
    """

    text: str
    binding: ModelExecutable[M]
    config: ParseConfig = DEFAULT_CONFIG


def split_parse[M: IrNamedTuple](
    parse: ModelParse[M],
    plan: SplitPlan,
    ask: Request[M],
    cuts: list[int],
    pool: WorkPool,
) -> M | None:
    """One split attempt; ``None`` means: parse sequentially instead."""
    text, binding, config = ask
    terminated = plan.terminated
    spans, leads = cut_spans(plan, text, cuts)
    if not terminated and plan.lead_grammar is None:
        if any(lead != plan.lead_literal for lead in leads):
            return None
    try:
        chunks = pool.map(
            lambda k: worker_parse(
                parse,
                plan.grammar,
                text[spans[k][0] : spans[k][1]],
                binding,
                config,
            ),
            list(range(len(spans))),
        )
        if plan.envelope is not None:
            return _envelope_join(parse, plan, ask, (chunks, leads))
        lead_models = [
            (parse(plan.lead_grammar, lead, binding, config),)
            if plan.lead_grammar is not None
            else ()
            for lead in leads
        ]
    except LexicError:
        return None
    if terminated:
        return stitch_terminated(chunks)
    return stitch_routed(chunks, lead_models, plan.wrappers, binding)


RETRIES = 2
"""Re-selections allowed per proposed cut before the split gives up on it.

Bounded because a wrong proposal costs a wasted piece parse and a right one
costs nothing — the parse IS the split work. Two is enough to step past a
character that merely LOOKS like a unit opening without letting a document of
near-misses out-cost the sequential parse it is racing."""


def _piece[M: IrNamedTuple](
    parse: ModelParse[M], grammar: IrAst, text: str, ask: Request[M]
) -> M | None:
    """One piece's model, or ``None`` when it refuses.

    A refusal here is a verdict on the CUT, never on the input: the piece was
    handed a span that may not begin a unit. The caller retries or declines,
    and the caller's sequential parse is what raises.
    """
    try:
        return worker_parse(parse, grammar, text, ask.binding, ask.config)
    except LexicError:
        return None


def _attempt[M: IrNamedTuple](
    parse: ModelParse[M],
    plan: SplitPlan,
    ask: Request[M],
    spans: list,
    pool: WorkPool,
) -> tuple[list, int]:
    """Parse every piece; the models, and the first failing index (``-1`` none)."""
    text = ask.text
    found = pool.map(
        lambda k: _piece(parse, plan.grammar, text[spans[k][0] : spans[k][1]], ask),
        list(range(len(spans))),
    )
    return found, next((k for k, one in enumerate(found) if one is None), -1)


def _reselect(
    text: str, marks: list[int], cuts: list[int], at: int
) -> list[int] | None:
    """``cuts`` with cut ``at`` moved to the next-nearest usable proposal.

    Only the two pieces this cut bounds may move, so its neighbours fix the
    room it has, and the floor binds on both sides of the new position exactly
    as it bound on the old one.
    """
    lo = cuts[at - 1] if at else 0
    hi = cuts[at + 1] if at + 1 < len(cuts) else len(text)
    taken = set(cuts)
    room = [
        candidate
        for candidate in marks
        if candidate not in taken and clears_floor((candidate - lo, hi - candidate))
    ]
    if not room:
        return None
    nearest = min(room, key=lambda candidate: (abs(candidate - cuts[at]), candidate))
    return [nearest if k == at else cut for k, cut in enumerate(cuts)]


def _speculate[M: IrNamedTuple](
    parse: ModelParse[M],
    plan: SplitPlan,
    ask: Request[M],
    proposed: Cuts,
    pool: WorkPool,
) -> M | None:
    """Verify proposed cuts by parsing, re-selecting a failing one, bounded.

    Acceptance is NOT the stitch looking right. It is the plan's precondition
    (segmentation of ``unit+`` is forced) plus every piece parsing: the pieces
    then exhibit the document's ONLY reading, so their concatenation is the
    model the sequential parse would have built — which is why the stitch is
    :func:`~...stitch.model.stitch_terminated` unchanged, with nothing
    inspected after the fact.

    :param proposed: The chosen cuts, and every candidate they were chosen from.
    :returns: The model, or ``None`` to decline to sequential.
    """
    cuts, marks = proposed
    spent = dict.fromkeys(range(len(cuts)), 0)
    for _round in range(len(cuts) + 1):
        chunks, failed = _attempt(
            parse, plan, ask, cut_spans(plan, ask.text, cuts)[0], pool
        )
        if failed < 0:
            return stitch_terminated(chunks)
        # A wrong cut fails BOTH pieces it bounds — the one before it ends
        # mid-unit, the one after begins mid-unit — so the FIRST failing piece
        # is the one whose END is wrong, and that end is the cut to move. The
        # final piece has no end of its own and answers for the cut before it.
        at = min(failed, len(cuts) - 1)
        if spent[at] >= RETRIES:
            return None
        spent[at] += 1
        moved = _reselect(ask.text, marks, cuts, at)
        if moved is None:
            return None
        cuts = moved
    return None


SPARE_FROM = 8
"""The CPU count from which a pool that claims every CPU spares one for the
calling thread, which parses the shell beside the pieces. Sparing costs one
piece in ``workers``: on 16 CPUs, 15 pieces measured about 12 percent faster
than 16; on 4, 3 pieces for 4 workers measured 25 to 30 percent slower."""


def piece_count(workers: int) -> int:
    """How many pieces a split plans for ``workers``: one fewer only when the
    pool claims every CPU and there are enough that one piece is a small share."""
    spare = workers >= available_workers() >= SPARE_FROM
    return workers - 1 if spare else workers


class _Units[M](NamedTuple):
    """What a region split parsed: the regions kept, their units, each piece's
    model in unit order, and the shell's."""

    works: list[RegionWork]
    plan: list[Unit]
    pieces: list[GrammarModel]
    whole: M


def _leaves(
    text: str, bound: list[RegionWork]
) -> dict[tuple[int, int], tuple[IrAst, str]]:
    """The pieces that hold no other region, keyed by their region's opener
    and their place in it: their text is final whatever stand-ins are chosen."""
    early = units(text, [Division(w.region, w.cuts) for w in bound], [""] * len(bound))
    return {
        key: (bound[unit.owner].plan.root, unit.text)
        for key, unit in _keyed(bound, early[:-1])
        if not unit.held
    }


def _keyed(
    works: list[RegionWork], pieces: list[Unit]
) -> list[tuple[tuple[int, int], Unit]]:
    """Each piece with its key: its region's opener, and its place among that
    region's pieces — the same in any plan that keeps the region."""
    seen: dict[int, int] = {}
    out: list[tuple[tuple[int, int], Unit]] = []
    for unit in pieces:
        place = seen.get(unit.owner, 0)
        seen[unit.owner] = place + 1
        out.append(((works[unit.owner].region.opener, place), unit))
    return out


class _Overlap[M: IrNamedTuple](NamedTuple):
    """One region split's units in flight: the tasks sent so far (the leaves
    first), each leaf's task by key, and what the calling thread chose.

    :ivar grammar: The document's grammar, the shell's.
    :ivar merge: The parse service and document.
    :ivar bound: The regions with a safe plan, before stand-ins.
    :ivar tasks: ``(grammar, text)`` per task, in submission order.
    :ivar early: Each leaf's key → its task.
    :ivar chosen: Once chosen: the regions kept, their units, and each piece's
        task.
    :ivar shell: The shell's model, once parsed.
    """

    grammar: IrAst
    merge: MergeRequest[M]
    bound: list[RegionWork]
    tasks: list[tuple[IrAst, str]]
    early: dict[tuple[int, int], int]
    chosen: list[tuple[list[RegionWork], list[Unit], list[int]]]
    shell: list[M]

    def beside(self, submit: Callable[[Sequence[int]], None]) -> bool:
        """The calling thread's share: choose the stand-ins, send the pieces
        that hold a region, parse the shell — or decline at once when no
        region keeps a stand-in, never waiting on the leaves."""
        merge, tasks = self.merge, self.tasks
        works = assign_witnesses(merge, self.bound)
        if not works:
            return False
        divided = [Division(work.region, work.cuts) for work in works]
        plan = units(merge.text, divided, [work.witness for work in works])
        where: list[int] = []
        for key, unit in _keyed(works, plan[:-1]):
            k = self.early.get(key, -1) if not unit.held else -1
            if k < 0 or tasks[k][1] != unit.text:
                k = len(tasks)
                tasks.append((works[unit.owner].plan.root, unit.text))
                submit([k])
            where.append(k)
        self.chosen.append((works, plan, where))
        self.shell.append(merge.run(self.grammar, plan[-1].text))
        return True


def _parse_units[M: IrNamedTuple](
    grammar: IrAst,
    merge: MergeRequest[M],
    bound: list[RegionWork],
    ask: Request[M],
    pool: WorkPool,
) -> _Units[M] | None:
    """Parse the pieces that need no stand-in at once, and choose the
    stand-ins on the calling thread while they run; then the pieces that hold
    a region, and the shell beside them.

    A leaf piece's text is the same whichever stand-ins are chosen, so it is
    parsed before they are. A region left without one has its leaves parsed
    for nothing and its text returned to its holder — rendered only after the
    choice, so exactly as if it had never divided. A piece's refusal is
    therefore only an answer once its region is kept: each piece answers
    ``None`` rather than raising, a kept piece's ``None`` declines the split
    as before, and a dropped region's is never read. The shell stays on this
    thread because it is parsed under the whole grammar, whose view this
    thread already holds: in the pool, whichever worker drew it would build a
    replica of the whole grammar for one small parse.
    """
    leaves = _leaves(ask.text, bound)
    run = _Overlap(
        grammar,
        merge,
        bound,
        list(leaves.values()),
        {k: i for i, k in enumerate(leaves)},
        [],
        [],
    )
    tasks = run.tasks
    try:
        parsed = pool.map(
            lambda k: _piece(merge.parse, tasks[k][0], tasks[k][1], ask),
            list(range(len(tasks))),
            run.beside,
        )
    except LexicError:
        return None
    if not run.chosen:
        return None
    works, plan, where = run.chosen[0]
    pieces = [model for k in where if isinstance(model := parsed[k], GrammarModel)]
    if len(pieces) != len(where):
        return None
    return _Units(works, plan, pieces, run.shell[0])


def split_regions[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Request[M],
    analysis: IrAst | None,
    pool: WorkPool,
) -> M | None:
    """Split eligible nested bracket regions; ``None`` means sequential.

    Reached only once every plan has declined, and then routed before the
    sweep: it is proof-certified against the start rule's own shape, where
    :func:`~...discovery.regions.partition` is a size heuristic over whatever
    brackets a document happens to contain.

    The cascade's rule is FIRST MATCH AMONG SURVIVORS, and the survivor set is
    fixed at DERIVATION rather than by trying things: one certified family
    survives — terminated, else separated, else envelope, a fixed preference
    and not a choice by fitness, so a family the ``or`` drops never returns —
    then proposals are appended after it, and a safety proof filters what is
    left, which can drop a certified plan while keeping a proposal.

    :func:`split_plan` returns the FIRST survivor, so a caller there sees one
    plan where this loop tries them all; the two agree wherever the first wins.
    """
    workers = pool.workers
    sourced = source_split(parse, grammar, ask, pool)
    if sourced is not None:
        return sourced
    # A bracket span may cover the whole source while still sit BELOW a
    # wrapper start model (``root ::= node``). Routing, not byte position,
    # decides whether it has a replaceable owner; a true root-region model
    # yields no non-empty route and declines in ``stitch_units``.
    found = [
        region
        for region in par_find(
            analysis or grammar, ask.text, 2 * MIN_CHUNK, workers, pool
        )
        if region.rule != str(grammar.start)
    ]
    divided = partition(ask.text, found, piece_count(workers))
    merge = MergeRequest(parse, ask.text, ask.binding, ask.config)
    bound = bound_works(merge, grammar, divided, analysis or grammar)
    if not bound:
        return None
    done = _parse_units(grammar, merge, bound, ask, pool)
    if done is None:
        return None
    return stitch_units(merge, done.works, done.plan, done.pieces, done.whole)


def split_model[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Request[M],
    cores: int = AUTO,
    *,
    analysis: IrAst | None = None,
) -> M | None:
    """Split this input across workers, or say the split does not apply.

    Returns exactly what :func:`~lexic.parsing.products.parse_model` returns
    for this input, with the wall-clock divided across workers, whenever a
    plan exists, the policy grants more than one worker, and every chunk
    parses. ``None`` says the caller should parse sequentially: no plan, too
    few cut points, or a chunk that failed — and a chunk failing is not a
    verdict on the input, only on the split, so the caller's sequential
    parse is what raises (or does not).

    :param parse: The model product, injected by the layer that owns it.
    :param grammar: The codegen grammar.
    :param ask: The document, its bound product and the configuration.
    :param cores: 0 = auto, 1 = sequential (so: never split), N = that many.
    :param analysis: A language-equivalent structural view for derived grammars
        whose parse model intentionally elides quoted interiors or wrappers.
    :returns: The model, or ``None`` to parse sequentially.
    """
    # Settle the universal gates before deriving a plan. Reducer folds can
    # issue thousands of tiny SubRun parses; under the GIL every one has one
    # worker, and under AUTO a sub-2-chunk input cannot divide. Asking roles,
    # ownership and region safety for work that policy has already refused is
    # pure serial overhead on the caller's parse path.
    workers = doc_workers(cores)
    if workers < 2 or capacity(len(ask.text)) < 2:
        return None
    # The plans and the proofs they rest on (a cut that speculation proposes is
    # trusted on a determinism read off the leftmost-longest analysis) are this
    # order's: another decider parses whole.
    if not isinstance(ask.config.decide, LeftmostLongest):
        return None
    licensed = safe_plans(split_plans(grammar), analysis or grammar)
    with PoolLease(workers) as pool:
        # Copies the workers owe from this pool's last split of a document of
        # this grammar are made now, all at once and before any piece goes out,
        # so none lands inside a piece.
        warm_due(pool, grammar)
        try:
            return _split_on(parse, grammar, ask, (cores, analysis, licensed), pool)
        finally:
            settle_first_meetings(pool, grammar)


def _split_on[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Request[M],
    setting: tuple[int, IrAst | None, tuple[SplitPlan, ...]],
    pool: WorkPool,
) -> M | None:
    """The plans in order, then the regions, on one lent pool."""
    cores, analysis, licensed = setting
    workers = pool.workers
    shared = shared_scanner(grammar, licensed)
    # The rebase belongs to the document, not to a plan: it reads only the
    # windows' marks and deltas, so every plan reading the sweep recomputed
    # the same offsets over every mark in the document.
    rebased = rebase(shared, ask.text, workers, pool) if shared is not None else None
    for plan in licensed:
        # Only a plan that reads a windowed sweep is handed the shared
        # offsets; a walking scan owns its pass, and an envelope plan reads
        # neither.
        seen = rebased if reads_a_sweep(plan) else None
        chosen = cut_offsets(plan, ask.text, cores, pool, seen)
        if not chosen.offsets:
            continue
        model = (
            _speculate(parse, plan, ask, chosen, pool)
            if plan.opening
            else split_parse(parse, plan, ask, chosen.offsets, pool)
        )
        if model is not None:
            return model
    return split_regions(parse, grammar, ask, analysis, pool)


def _envelope_join[M: IrNamedTuple](
    parse: ModelParse[M],
    plan: SplitPlan,
    ask: Request[M],
    parsed: tuple[list, list[str]],
) -> M | None:
    """Reparse each separator with the noise its piece absorbed, then stitch.

    The piece kept the mark and the noise before it; that text comes back out,
    goes in front of the separator, and reparses under the repeated item with a
    witness unit the stitch swaps for the next piece's real head.
    """
    found = plan.envelope
    repeated = plan.lead_grammar
    chunks, leads = parsed
    moved = envelope_tails(chunks, found.shape, ask.binding) if found else None
    # An envelope plan carries the repeated item as its lead grammar; without
    # one there is nothing to reparse the separators under, so this declines
    # exactly as any other unsupported shape does.
    if found is None or moved is None or repeated is None:
        return None
    tails, trimmed = moved
    witness = unit_witness(plan.grammar, found.shape.unit) or ""
    rebuilt = [
        parse(repeated, tails[at] + lead + witness, ask.binding, ask.config)
        for at, lead in enumerate(leads)
    ]
    return stitch_envelope(trimmed, rebuilt, found.shape, ask.binding)
