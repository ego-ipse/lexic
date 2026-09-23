"""One-document model splitting and exact immutable stitching.

Start-rule repetitions and nested bracketed regions share this one entry.
Delegated interiors are removed from the enclosing shell before it parses;
non-overlapping ownership prevents parent and child workers duplicating work.
Every unsupported shape or failed piece declines to the caller's sequential
parse, so worker count never changes what an input means.
"""

from __future__ import annotations

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
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.discovery.regions import par_find
from lexic.parsing.parallel.partition import Division, partition, units
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
from lexic.parsing.parallel.policy import AUTO, MIN_CHUNK, doc_workers
from lexic.parsing.parallel.pool import PoolLease, WorkPool
from lexic.parsing.parallel.replicas import worker_parse
from lexic.parsing.parallel.stitch.interior import source_split
from lexic.parsing.parallel.stitch.merge import MergeRequest, stitch_units
from lexic.parsing.parallel.stitch.model import (
    envelope_tails,
    stitch_envelope,
    stitch_routed,
    stitch_terminated,
)
from lexic.parsing.parallel.stitch.tasks import region_tasks, region_works


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


def _split_parse[M: IrNamedTuple](
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
        if candidate not in taken
        and candidate - lo >= MIN_CHUNK
        and hi - candidate >= MIN_CHUNK
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


def _parse_units[M: IrNamedTuple](
    parse: ModelParse[M],
    tasks: list[tuple[IrAst, str]],
    ask: Request[M],
    pool: WorkPool,
) -> tuple[list[GrammarModel], M] | None:
    """Parse every unit concurrently against per-worker replicas — the pieces
    of every level AND the shell in one map, so the shell is not left for
    after them."""
    try:
        parsed = pool.map(
            lambda k: worker_parse(
                parse, tasks[k][0], tasks[k][1], ask.binding, ask.config
            ),
            list(range(len(tasks))),
        )
    except LexicError:
        return None
    pieces = [model for model in parsed[:-1] if isinstance(model, GrammarModel)]
    if len(pieces) != len(parsed) - 1:
        return None
    return pieces, parsed[-1]


def _split_regions[M: IrNamedTuple](
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
    if workers < 2 or len(ask.text) < 2 * MIN_CHUNK:
        return None
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
    divided = partition(ask.text, found, workers)
    merge = MergeRequest(parse, ask.text, ask.binding, ask.config)
    works = region_works(merge, grammar, divided, analysis or grammar)
    if not works:
        return None
    plan = units(
        ask.text,
        [Division(work.region, work.cuts) for work in works],
        [work.witness for work in works],
    )
    parsed = _parse_units(parse, region_tasks(grammar, works, plan), ask, pool)
    return stitch_units(merge, works, plan, *parsed) if parsed is not None else None


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
    if workers < 2 or len(ask.text) < 2 * MIN_CHUNK:
        return None
    licensed = safe_plans(split_plans(grammar), analysis or grammar)
    with PoolLease(workers) as pool:
        shared = shared_scanner(grammar, licensed)
        # The rebase belongs to the document, not to a plan: it reads only the
        # windows' marks and deltas, so every plan reading the sweep recomputed
        # the same offsets over every mark in the document.
        rebased = (
            rebase(shared, ask.text, workers, pool) if shared is not None else None
        )
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
                else _split_parse(parse, plan, ask, chosen.offsets, pool)
            )
            if model is not None:
                return model
        return _split_regions(parse, grammar, ask, analysis, pool)


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
