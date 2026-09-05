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
    IrItem,
    IrLiteral,
    IrNamedTuple,
    IrRule,
    IrRuleRef,
)
from lexic.model import GrammarModel
from lexic.parsing.caches import memo
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.discovery.regions import (
    choose,
    find,
)
from lexic.parsing.parallel.discovery.scan import Scanner
from lexic.parsing.parallel.discovery.shapes import UNIT, unbounded
from lexic.parsing.parallel.plan.cuts import (
    cut_offsets,
    cut_spans,
    scan_marks,
    scan_windows,
    sole_mark,
)
from lexic.parsing.parallel.plan.envelope import (
    envelope_plans,
    unit_witness,
)
from lexic.parsing.parallel.plan.speculation import speculative_openings
from lexic.parsing.parallel.plan.split import SplitPlan, lead_skip, spellings
from lexic.parsing.parallel.policy import AUTO, MIN_CHUNK, doc_workers
from lexic.parsing.parallel.pool import PoolLease, WorkPool
from lexic.parsing.parallel.replicas import worker_parse
from lexic.parsing.parallel.roles import Roles, Separator, Terminator, roles
from lexic.parsing.parallel.stitch.interior import routed_split
from lexic.parsing.parallel.stitch.merge import MergeRequest, standins, stitch_shell
from lexic.parsing.parallel.stitch.model import (
    envelope_tails,
    stitch_envelope,
    stitch_routed,
    stitch_terminated,
)
from lexic.parsing.parallel.stitch.plan import RegionWork
from lexic.parsing.parallel.stitch.safety import (
    bounds_units,
    mark_interiors,
    mark_overlap,
    owner_excludes,
    scan_agrees,
    terminates_once,
    unit_boundary,
)
from lexic.parsing.parallel.stitch.tasks import region_tasks, region_works


class Request[M: IrNamedTuple](NamedTuple):
    """One split parse's per-call inputs — what changes between documents.

    Bundled because the plan, the product and the request are three
    different lifetimes: the product is fixed, the plan is per grammar, and
    only this varies per call.

    :ivar text: The document.
    :ivar binding: The bound model product producing ``M``.
    :ivar resolve: The caller's ambiguity resolver, or ``None``.
    """

    text: str
    binding: ModelExecutable[M]
    resolve: Resolver | None = None


def _unit_ref(item: IrItem) -> str | None:
    """The unit rule an item references, when it is a plain unit reference."""
    atom = item.atom
    if isinstance(atom, IrRuleRef) and item.quantifier == UNIT:
        return str(atom)
    return None


def _single_arm(rule: IrRule) -> tuple[IrItem, ...] | None:
    """The rule's only arm, when it has exactly one."""
    arms = tuple(rule.body)
    return tuple(arms[0]) if len(arms) == 1 else None


def _item_shape(rule: IrRule, sep: Separator, unit: str) -> bool:
    """Whether the repeated rule is ``lead unit`` for this separator."""
    items = _single_arm(rule)
    if items is None or len(items) != 2 or _unit_ref(items[1]) != unit:
        return False
    lead_atom = items[0].atom
    if sep.lead:
        return _unit_ref(items[0]) == sep.lead
    return isinstance(lead_atom, IrLiteral) and str(lead_atom) == sep.mark


def _wrapper_chain(
    rule_map: dict[str, IrRule], start: str, target: str
) -> tuple[str, ...] | None:
    """Head-reference route from ``start`` through empty-capable tails."""
    wrappers: list[str] = []
    seen: set[str] = set()
    current = start
    while current != target:
        rule = rule_map.get(current)
        items = _single_arm(rule) if rule is not None else None
        child = _unit_ref(items[0]) if items else None
        empty_tails = items is not None and all(
            unbounded(item) and item.quantifier.lo == 0 for item in items[1:]
        )
        if child is None or not empty_tails or current in seen:
            return None
        seen.add(current)
        wrappers.append(current)
        current = child
    return tuple(wrappers)


def _plan_for(
    grammar: IrAst, sep: Separator, rule_map: dict[str, IrRule]
) -> SplitPlan | None:
    """The plan one separator record admits, or ``None`` on a shape miss."""
    container = rule_map.get(sep.container)
    item_rule = rule_map.get(sep.item)
    if container is None or item_rule is None:
        return None
    wrappers = _wrapper_chain(rule_map, str(grammar.start), sep.container)
    if wrappers is None:
        return None
    items = _single_arm(container)
    if items is None or len(items) != 2:
        return None
    unit = _unit_ref(items[0])
    repeated = items[1].atom
    repeats = isinstance(repeated, IrRuleRef) and str(repeated) == sep.item
    if unit is None or not repeats or not _item_shape(item_rule, sep, unit):
        return None
    if sep.lead:
        lead_grammar, literal = IrAst(grammar.rules, sep.lead), ""
        skip = lead_skip(_single_arm(rule_map[sep.lead]), rule_map, sep.mark)
    else:
        lead_grammar, literal = None, sep.mark
        skip = frozenset()
    return SplitPlan(
        grammar,
        Scanner(roles(grammar)),
        frozenset({sep.mark}),
        spellings(frozenset({sep.mark})),
        unit,
        wrappers,
        sep,
        lead_grammar,
        literal,
        skip,
    )


def _terminated_plans(
    grammar: IrAst, rule_map: dict[str, IrRule]
) -> tuple[SplitPlan, ...]:
    """The plans a ``start ::= unit+`` terminated repetition admits.

    The start rule's only arm must be one unbounded reference to a unit that
    ends with an agreed anchor mark. Cuts land after the terminator, so each
    chunk holds whole units and parses under the start rule unchanged.
    Terminators a certified delimited region hides go to the scanner instead.

    One plan per agreed spelling, narrowest first: which of them a grammar can
    prove is the safety cascade's question, not this one's.
    """
    start = rule_map.get(str(grammar.start))
    if start is None:
        return ()
    items = _single_arm(start)
    if items is None or len(items) != 1 or not unbounded(items[0]):
        return ()
    target = items[0].atom
    if not isinstance(target, IrRuleRef):
        return ()
    derived = roles(grammar)
    unit = str(target)
    return tuple(
        SplitPlan(
            grammar,
            Scanner(derived, mark_interiors(grammar, unit, record.mark)),
            record.mark,
            spellings(record.mark),
            unit,
            (),
            None,
            None,
            "",
            frozenset(),
        )
        for record in derived.terminators
        if record.unit == unit and record.container == str(grammar.start)
    )


def _speculative_plans(
    grammar: IrAst, rule_map: dict[str, IrRule]
) -> tuple[SplitPlan, ...]:
    """The plan a ``start ::= unit+`` repetition admits by PROPOSAL.

    Read last, and only where every other route declined: this is the one plan
    whose cuts are candidates rather than boundaries, and it pays a piece parse
    to find out. The precondition it rests on is
    :func:`~...plan.speculation.speculative_openings`; an empty answer is the
    ordinary decline.

    The scan needs no new machinery — it sweeps a set of spellings already, so
    the unit's opening alphabet goes in where a terminator's would.
    """
    start = rule_map.get(str(grammar.start))
    items = _single_arm(start) if start is not None else None
    if items is None or len(items) != 1 or not unbounded(items[0]):
        return ()
    target = items[0].atom
    if not isinstance(target, IrRuleRef):
        return ()
    unit = str(target)
    openings = speculative_openings(grammar, unit)
    if not openings:
        return ()
    derived = roles(grammar)
    proposals = Roles(
        derived.pairs, (), (Terminator(openings, str(grammar.start), unit),)
    )
    return (
        SplitPlan(
            grammar,
            Scanner(proposals),
            openings,
            spellings(openings),
            unit,
            (),
            None,
            None,
            "",
            frozenset(),
            opening=True,
        ),
    )


_PLANS: dict[int, tuple[IrAst, tuple[SplitPlan, ...]]] = memo({})
"""Plan memo — id(grammar) → (grammar, plans). The strong reference pins the
id, so a recycled id can never alias a live entry."""


def _split_plans(grammar: IrAst) -> tuple[SplitPlan, ...]:
    """Every exact start-reachable plan, memoised per grammar identity."""
    entry = _PLANS.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        terminated = _terminated_plans(grammar, rule_map)
        separated = tuple(
            plan
            for sep in roles(grammar).records
            if sep.item and (plan := _plan_for(grammar, sep, rule_map)) is not None
        )
        wrapped = _envelope_split_plan(grammar)
        proposed = _speculative_plans(grammar, rule_map)
        # Proposals are APPENDED, never an alternative: a derived plan that
        # then fails certification must not shadow them, and a certified one
        # must still be tried first — a proposal pays a piece parse to learn
        # what a proof already knows.
        plans = (terminated or separated or wrapped) + proposed
        entry = (grammar, plans)
        _PLANS[id(grammar)] = entry
    return entry[1]


def split_plan(grammar: IrAst) -> SplitPlan | None:
    """The grammar's split plan, memoised per identity; ``None`` = sequential.

    :param grammar: The codegen grammar (repetitions hoisted to rules).
    :returns: A plan when the START rule is a separated repetition whose
        shape the stitch supports; ``None`` otherwise.
    """
    plans = _split_plans(grammar)
    return plans[0] if plans else None


def _split_parse[M: IrNamedTuple](
    parse: ModelParse[M],
    plan: SplitPlan,
    ask: Request[M],
    cuts: list[int],
    pool: WorkPool,
) -> M | None:
    """One split attempt; ``None`` means: parse sequentially instead."""
    text, binding, resolve = ask
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
                resolve,
            ),
            list(range(len(spans))),
        )
        if plan.envelope is not None:
            return _envelope_join(parse, plan, ask, (chunks, leads))
        lead_models = [
            (parse(plan.lead_grammar, lead, binding, resolve),)
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
        return worker_parse(parse, grammar, text, ask.binding, ask.resolve)
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
    proposed: tuple[list[int], list[int]],
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


def _parse_region_parts[M: IrNamedTuple](
    parse: ModelParse[M],
    works: list[RegionWork],
    ask: Request[M],
    pool: WorkPool,
) -> list[list[GrammarModel]] | None:
    """Parse every region piece concurrently against per-worker replicas."""
    tasks, owners = region_tasks(works)
    try:
        parsed = pool.map(
            lambda k: worker_parse(
                parse, tasks[k][0], tasks[k][1], ask.binding, ask.resolve
            ),
            list(range(len(tasks))),
        )
    except LexicError:
        return None
    grouped: list[list[GrammarModel]] = [[] for _work in works]
    for owner, model in zip(owners, parsed, strict=True):
        if not isinstance(model, GrammarModel):
            return None
        grouped[owner].append(model)
    return grouped


def _split_regions[M: IrNamedTuple](
    parse: ModelParse[M],
    grammar: IrAst,
    ask: Request[M],
    analysis: IrAst | None,
    pool: WorkPool,
) -> M | None:
    """Split eligible nested bracket regions; ``None`` means sequential.

    The routed region is tried FIRST, and a successful one never pays for the
    sweep. The plan cascade is ordered by certainty — terminated, separated,
    envelope, then regions — and a routed region belongs at the certain end: it
    is proof-certified against the start rule's own shape, where the sweep's
    :func:`~...discovery.regions.choose` is a size heuristic over whatever
    brackets a document happens to contain. A certified source outranks a
    speculative one wherever both apply.
    """
    workers = pool.workers
    if workers < 2 or len(ask.text) < 2 * MIN_CHUNK:
        return None
    routed = routed_split(parse, grammar, (ask.text, ask.binding, ask.resolve), pool)
    if routed is not None:
        return routed
    # A bracket span may cover the whole source while still sit BELOW a
    # wrapper start model (``root ::= node``). Routing, not byte position,
    # decides whether it has a replaceable owner; a true root-region model
    # yields no non-empty route and declines in ``_stitch_shell``.
    found = [
        region
        for region in find(analysis or grammar, ask.text, 2 * MIN_CHUNK)
        if region.rule != str(grammar.start)
    ]
    divided = choose(ask.text, found, workers)
    works = region_works(grammar, ask.binding, ask.text, divided, analysis or grammar)
    if works is None:
        return None
    parsed = _parse_region_parts(parse, works, ask, pool)
    merge = MergeRequest(parse, ask.text, ask.binding, ask.resolve)
    stands = standins(merge, works, parsed) if parsed is not None else None
    return stitch_shell(merge, grammar, works, stands) if stands else None


def _certified(plan: SplitPlan, view: IrAst) -> SplitPlan | None:
    """The plan a safety proof licenses over ``view``, or ``None`` to drop it.

    Each shape owes a different proof, and a TERMINATED plan owes either of
    two. The first is that its unit emits the mark ONLY as its own final edge
    (``terminates_once``), which makes every mark a boundary and needs no
    filter. Failing that, the unit may still ANNOUNCE itself — the boundary
    proof — and the plan carries that prefix so :func:`_cut_offsets` can admit
    the marks that begin a unit and refuse the ones that do not. A unit with
    neither is what it always was: not splittable on this mark.
    """
    if plan.opening:
        # A proposal owes no boundary proof — the piece parse settles whether
        # it was right — but it owes the same AGREEMENT ``scan_agrees`` owes:
        # the precondition is derived on the grammar the pieces parse under,
        # and a caller-supplied view that licenses a different opening
        # alphabet is describing a different language, not a stricter one.
        return plan if speculative_openings(view, plan.owner) == plan.mark else None
    mark = sole_mark(plan)
    if plan.envelope is not None:
        return plan if unit_boundary(view, plan.owner, mark) is not None else None
    if plan.sep is None:
        return _certified_terminated(plan, view, mark)
    if not owner_excludes(view, plan.owner, mark):
        return None
    overlap = mark_overlap(view, plan.owner, mark)
    return plan._replace(trailing=overlap.trailing) if overlap.decided else None


def _certified_terminated(plan: SplitPlan, view: IrAst, mark: str) -> SplitPlan | None:
    """The three routes a terminated plan may be licensed by, in order.

    The agreed terminator first — every mark is a boundary and no filter is
    needed. Then the unit's whole ending alphabet, where the arms close
    differently and no ending character stands anywhere but at an end. Failing
    both, the unit may still ANNOUNCE itself, and the plan carries that prefix
    so the cut selection can admit the marks that begin a unit.
    """
    if (
        mark
        and terminates_once(view, plan.owner, mark)
        and scan_agrees(view, plan.grammar, plan.owner, plan.mark)
    ):
        return plan
    if bounds_units(view, plan.owner, plan.mark):
        return plan
    bound = unit_boundary(view, plan.owner, mark) if mark else None
    return None if bound is None else plan._replace(bound=bound)


def _safe_plans(plans: tuple[SplitPlan, ...], view: IrAst) -> tuple[SplitPlan, ...]:
    """Every plan a safety proof licenses over ``view``, in cascade order."""
    return tuple(
        certified for plan in plans if (certified := _certified(plan, view)) is not None
    )


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
    :param ask: The document, its bound product, and the ambiguity resolver.
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
    safe_plans = _safe_plans(_split_plans(grammar), analysis or grammar)
    with PoolLease(workers) as pool:
        windows = (
            scan_windows(safe_plans[0].scanner, ask.text, workers, pool)
            if safe_plans
            else None
        )
        for plan in safe_plans:
            # A proposal scans for its own opening alphabet, which is not in
            # the roles the shared window pass swept.
            seen = (
                scan_windows(plan.scanner, ask.text, workers, pool)
                if plan.opening
                else windows
            )
            cuts = cut_offsets(plan, ask.text, cores, pool, seen)
            if not cuts:
                continue
            model = (
                _speculate(
                    parse,
                    plan,
                    ask,
                    (cuts, scan_marks(plan, ask.text, workers, pool, seen)),
                    pool,
                )
                if plan.opening
                else _split_parse(parse, plan, ask, cuts, pool)
            )
            if model is not None:
                return model
        return _split_regions(parse, grammar, ask, analysis, pool)


def _envelope_split_plan(grammar: IrAst) -> tuple[SplitPlan, ...]:
    """The plans an envelope container with a noise-run separator admits.

    Read last: a grammar whose start rule is a plain repetition is already
    served, and this shape costs a boundary proof to certify. One plan per
    PROVABLE mark — which of them a document actually carries is the
    orchestrator's question, settled by the first that yields cuts.
    """
    derived = roles(grammar)
    return tuple(
        SplitPlan(
            grammar,
            Scanner(derived),
            frozenset({found.mark}),
            spellings(frozenset({found.mark})),
            found.shape.unit,
            (),
            None,
            found.run.target,
            "",
            frozenset(),
            found,
        )
        for found in envelope_plans(grammar, str(grammar.start))
    )


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
        parse(repeated, tails[at] + lead + witness, ask.binding, ask.resolve)
        for at, lead in enumerate(leads)
    ]
    return stitch_envelope(trimmed, rebuilt, found.shape, ask.binding)
