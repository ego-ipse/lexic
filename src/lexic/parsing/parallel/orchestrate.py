"""One-document model splitting and exact immutable stitching.

Start-rule repetitions and nested bracketed regions share this one entry.
Delegated interiors are removed from the enclosing shell before it parses;
non-overlapping ownership prevents parent and child workers duplicating work.
Every unsupported shape or failed piece declines to the caller's sequential
parse, so worker count never changes what an input means.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterator
from typing import Any, NamedTuple

from lexic.exceptions import LexicError
from lexic.ir import (
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNamedTuple,
    IrRule,
    IrRuleRef,
    IrSelf,
)
from lexic.model import GrammarModel
from lexic.parsing.caches import memo
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.fold import ModelFold
from lexic.parsing.parallel.discovery.regions import (
    choose,
    find,
)
from lexic.parsing.parallel.discovery.scan import Scanner, Window
from lexic.parsing.parallel.discovery.shapes import UNIT, unbounded
from lexic.parsing.parallel.plan.envelope import (
    admits,
    envelope_plans,
    unit_witness,
)
from lexic.parsing.parallel.plan.split import SplitPlan
from lexic.parsing.parallel.policy import AUTO, MIN_CHUNK, doc_workers, worker_count
from lexic.parsing.parallel.pool import PoolLease, WorkPool
from lexic.parsing.parallel.replicas import worker_replicas
from lexic.parsing.parallel.roles import Separator, roles
from lexic.parsing.parallel.stitch.interior import routed_split
from lexic.parsing.parallel.stitch.merge import MergeRequest, standins, stitch_shell
from lexic.parsing.parallel.stitch.model import (
    RegionWork,
    envelope_tails,
    stitch_envelope,
    stitch_routed,
    stitch_terminated,
)
from lexic.parsing.parallel.stitch.safety import (
    mark_interiors,
    owner_excludes,
    scan_agrees,
    terminates_once,
    unit_boundary,
)
from lexic.parsing.parallel.stitch.tasks import region_tasks, region_works
from lexic.parsing.pda.core.charsets import CharSet


class Request[M: IrNamedTuple](NamedTuple):
    """One split parse's per-call inputs — what changes between documents.

    Bundled because the plan, the product and the request are three
    different lifetimes: the product is fixed, the plan is per grammar, and
    only this varies per call.

    :ivar text: The document.
    :ivar fold: The instance fold producing ``M``.
    :ivar resolve: The caller's ambiguity resolver, or ``None``.
    """

    text: str
    fold: ModelFold[M]
    resolve: Resolver | None = None


ModelProduct = Callable[..., Any]
"""The model product, injected: this module splits products, never imports
them — that direction is what lets a product's own entry call into it."""


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
    return isinstance(lead_atom, IrLiteral) and str(lead_atom) == sep.char


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
        skip = _lead_skip(sep, rule_map)
    else:
        lead_grammar, literal = None, sep.char
        skip = frozenset()
    return SplitPlan(
        grammar,
        Scanner(roles(grammar)),
        sep.char,
        unit,
        wrappers,
        sep,
        lead_grammar,
        literal,
        skip,
    )


def _terminated_plan(grammar: IrAst, rule_map: dict[str, IrRule]) -> SplitPlan | None:
    """The plan a ``start ::= unit+`` terminated repetition admits.

    The start rule's only arm must be one unbounded reference to a unit that
    ends with a single anchor character. Cuts land after the terminator, so
    each chunk holds whole units and parses under the start rule unchanged.
    Terminators a certified delimited region hides go to the scanner instead.
    """
    start = rule_map.get(str(grammar.start))
    if start is None:
        return None
    items = _single_arm(start)
    if items is None or len(items) != 1 or not unbounded(items[0]):
        return None
    target = items[0].atom
    if not isinstance(target, IrRuleRef):
        return None
    derived = roles(grammar)
    unit = str(target)
    for record in derived.terminators:
        if record.unit == unit and record.container == str(grammar.start):
            return SplitPlan(
                grammar,
                Scanner(derived, mark_interiors(grammar, unit, record.char)),
                record.char,
                unit,
                (),
                None,
                None,
                "",
                frozenset(),
            )
    return None


def _atom_chars(atom: IrSelf) -> frozenset[str]:
    """The chars a literal or char-class atom can emit (co-finite: none).

    A starred literal (``" "*``) emits its chars just as a class does — the
    first skip derivation only looked at classes and missed json-style
    ``ws ::= " "*``, silently degrading every lead-rule split to fallback.
    """
    if isinstance(atom, IrLiteral):
        return frozenset(str(atom))
    if not isinstance(atom, IrCharClass):
        return frozenset()
    emits = CharSet.from_charclass(atom)
    return frozenset() if emits.negated else emits.chars


def _lead_skip(sep: Separator, rule_map: dict[str, IrRule]) -> frozenset[str]:
    """The chars the lead rule may consume AFTER its separator char.

    Only what the lead itself derives (``comma ::= "," ws`` → the ws
    charset) — the cut extends over exactly this noise, so the chunk starts
    where the unit starts. Over- or under-collection is safe: a lead or
    chunk that then fails to parse makes the whole attempt fall back.
    """
    items = _single_arm(rule_map[sep.lead])
    if items is None:
        return frozenset()
    out: set[str] = set()
    for item in items[1:]:
        atom = item.atom
        out |= _atom_chars(atom)
        if isinstance(atom, IrRuleRef) and str(atom) in rule_map:
            for arm in rule_map[str(atom)].body:
                for inner in arm:
                    out |= _atom_chars(inner.atom)
    return frozenset(out) - {sep.char}


_PLANS: dict[int, tuple[IrAst, tuple[SplitPlan, ...]]] = memo({})
"""Plan memo — id(grammar) → (grammar, plans). The strong reference pins the
id, so a recycled id can never alias a live entry."""


def _split_plans(grammar: IrAst) -> tuple[SplitPlan, ...]:
    """Every exact start-reachable plan, memoised per grammar identity."""
    entry = _PLANS.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        terminated = _terminated_plan(grammar, rule_map)
        separated = tuple(
            plan
            for sep in roles(grammar).records
            if sep.item and (plan := _plan_for(grammar, sep, rule_map)) is not None
        )
        wrapped = _envelope_split_plan(grammar)
        plans = (terminated,) if terminated is not None else separated or wrapped
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


def _scan_windows(
    scanner: Scanner, text: str, workers: int, pool: WorkPool
) -> list[Window]:
    """Scan windows once for every separator plan of one grammar.

    A scanner carrying opaque regions walks instead: a window cannot know
    whether it begins inside one, and only the previous mark can say.
    """
    if scanner.opaque:
        return [scanner.walk(text)]
    if workers < 2:
        return [scanner.window(text, 0, len(text))]
    step = len(text) // workers
    bounds = [
        (k * step, (k + 1) * step if k < workers - 1 else len(text))
        for k in range(workers)
    ]
    return pool.map(lambda span: scanner.window(text, span[0], span[1]), bounds)


def _scan(
    plan: SplitPlan,
    text: str,
    workers: int,
    pool: WorkPool,
    windows: list[Window] | None = None,
) -> list[int]:
    """Depth-0 marks of this plan's char, scanned over ``workers`` windows.

    Windows are arithmetic and each is scanned with no left context — a
    mark character is structural at every occurrence, so a window needs
    nothing from its predecessor and the prefix-sum rebase recovers the
    absolute depths. One window IS the sequential scan.
    """
    scanned = windows or _scan_windows(plan.scanner, text, workers, pool)
    return [
        offset
        for offset in plan.scanner.offsets(scanned, depth=0)
        if text[offset] == plan.mark
    ]


def _cut_offsets(
    plan: SplitPlan,
    text: str,
    cores: int,
    pool: WorkPool,
    windows: list[Window] | None = None,
) -> list[int]:
    """The chosen cut offsets — depth-0 marks of this plan's char, thinned.

    The worker CEILING is settled before anything is scanned: it depends
    only on the build, the core count and the input size, so a document
    that could never occupy two workers must not pay a scan to find that
    out — that scan is a full pass over the input, and charging it to every
    small parse is a regression on grammars that merely HAVE a plan.

    A terminated plan's final mark is dropped: cutting after the document's
    last terminator leaves an empty chunk, which is not a document.
    """
    ceiling = worker_count(len(text), len(text), cores)
    if ceiling < 2:
        return []
    if plan.envelope is not None:
        marks = plan.envelope.cuts(text)
    else:
        marks = _scan(plan, text, ceiling, pool, windows)
        if plan.bound is not None:
            # The unit emits its own mark, so a mark is a candidate rather
            # than a boundary: keep the ones a unit actually begins after.
            # A terminated unit starts immediately AFTER its mark — there is
            # no separator run to extend over, which is the envelope path's
            # only other difference.
            marks = [at for at in marks if admits(text, at + 1, plan.bound, plan.mark)]
    if plan.terminated and marks and marks[-1] == len(text) - 1:
        marks.pop()
    workers = worker_count(len(text), len(marks), cores)
    while workers >= 2:
        cuts = _balanced_cuts(plan, text, marks, workers)
        if cuts:
            return cuts
        workers -= 1
    return []


def _balanced_cuts(
    plan: SplitPlan, text: str, marks: list[int], workers: int
) -> list[int]:
    """Marks nearest equal byte targets, if every actual span clears policy."""
    cuts: list[int] = []
    previous = 0
    for k in range(1, workers):
        want = len(text) * k / workers
        remaining = workers - k
        nearest = _safe_mark(plan, text, marks, previous, (want, remaining))
        if nearest is None:
            return []
        cuts.append(nearest)
        previous = _after_mark(plan, text, nearest)
    spans, _leads = _spans(plan, text, cuts)
    return (
        cuts
        if len(spans) == workers and min(hi - lo for lo, hi in spans) >= MIN_CHUNK
        else []
    )


def _after_mark(plan: SplitPlan, text: str, mark: int) -> int:
    """First source offset owned by the piece after ``mark``."""
    if plan.envelope is not None:
        return plan.envelope.resumes(text, mark)
    after = mark + 1
    while after < len(text) and text[after] in plan.skip:
        after += 1
    return after


def _safe_mark(
    plan: SplitPlan,
    text: str,
    marks: list[int],
    previous: int,
    target: tuple[float, int],
) -> int | None:
    """Nearest target mark whose adjacent spans can still clear the floor."""
    want, remaining = target
    terminated = plan.terminated
    lo = bisect_left(marks, previous + MIN_CHUNK - int(terminated))
    hi = bisect_right(marks, len(text) - remaining * MIN_CHUNK - 1)
    for candidate in _nearby_marks(marks, want, lo, hi):
        after = _after_mark(plan, text, candidate)
        end = after if terminated else candidate
        if end - previous >= MIN_CHUNK and len(text) - after >= remaining * MIN_CHUNK:
            return candidate
    return None


def _nearby_marks(marks: list[int], want: float, lo: int, hi: int) -> Iterator[int]:
    """Yield candidates within ``[lo, hi)`` from nearest to farthest."""
    at = bisect_left(marks, want, lo, hi)
    left, right = at - 1, at
    while left >= lo or right < hi:
        take_left = right >= hi or (
            left >= lo and want - marks[left] <= marks[right] - want
        )
        yield marks[left] if take_left else marks[right]
        left -= int(take_left)
        right += int(not take_left)


def _spans(plan: SplitPlan, text: str, cuts: list[int]) -> tuple[list, list[str]]:
    """The chunk spans and each cut's carried lead text.

    A terminated unit OWNS its final character, so its chunk keeps it and
    carries no lead; a separated cut hands the separator (and the noise the
    lead owns) to the lead re-parse instead.
    """
    spans: list[tuple[int, int]] = []
    leads: list[str] = []
    prev = 0
    terminated = plan.terminated
    for cut in cuts:
        after = _after_mark(plan, text, cut)
        # An envelope piece KEEPS the mark: a separator that begins before one
        # (a comment closed by it) would otherwise straddle the cut, and the
        # piece's own tail is what absorbs the run before the join takes it.
        owned = cut + 1 if plan.envelope is not None else cut
        spans.append((prev, after if terminated else owned))
        leads.append("" if terminated else text[owned:after])
        prev = after
    spans.append((prev, len(text)))
    return spans, leads


def _split_parse[M: IrNamedTuple](
    parse: ModelProduct,
    plan: SplitPlan,
    ask: Request[M],
    cuts: list[int],
    pool: WorkPool,
) -> M | None:
    """One split attempt; ``None`` means: parse sequentially instead."""
    text, fold, resolve = ask
    terminated = plan.terminated
    spans, leads = _spans(plan, text, cuts)
    if not terminated and plan.lead_grammar is None:
        if any(lead != plan.lead_literal for lead in leads):
            return None
    # Each worker parses against its OWN equal grammar and fold copy: the
    # tables are read-only, but sharing one set of them across cores is what
    # flattens scaling at ~1.8x (refcount cache-line traffic, measured).
    views = worker_replicas(plan.grammar, fold, len(spans))
    try:
        chunks = pool.map(
            lambda k: parse(
                views[k][0], text[spans[k][0] : spans[k][1]], views[k][1], resolve
            ),
            list(range(len(spans))),
        )
        if plan.envelope is not None:
            return _envelope_join(parse, plan, ask, (chunks, leads))
        lead_models = [
            (parse(plan.lead_grammar, lead, fold, resolve),)
            if plan.lead_grammar is not None
            else ()
            for lead in leads
        ]
    except LexicError:
        return None
    if terminated:
        return stitch_terminated(chunks)
    return stitch_routed(chunks, lead_models, plan.wrappers, fold)


def _parse_region_parts[M: IrNamedTuple](
    parse: ModelProduct,
    works: list[RegionWork],
    ask: Request[M],
    pool: WorkPool,
) -> list[list[GrammarModel]] | None:
    """Parse every region piece concurrently against per-worker replicas."""
    tasks, owners = region_tasks(works, ask.fold)
    try:
        parsed = pool.map(
            lambda k: parse(tasks[k][0], tasks[k][2], tasks[k][1], ask.resolve),
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
    parse: ModelProduct,
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
    routed = routed_split(parse, grammar, (ask.text, ask.fold, ask.resolve), pool)
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
    works = region_works(grammar, ask.fold, ask.text, divided, analysis or grammar)
    if works is None:
        return None
    parsed = _parse_region_parts(parse, works, ask, pool)
    merge = MergeRequest(parse, ask.text, ask.fold, ask.resolve)
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
    if plan.envelope is not None:
        return plan if unit_boundary(view, plan.owner, plan.mark) is not None else None
    if plan.sep is not None:
        return plan if owner_excludes(view, plan.owner, plan.mark) else None
    if terminates_once(view, plan.owner, plan.mark) and scan_agrees(
        view, plan.grammar, plan.owner, plan.mark
    ):
        return plan
    bound = unit_boundary(view, plan.owner, plan.mark)
    return None if bound is None else plan._replace(bound=bound)


def _safe_plans(plans: tuple[SplitPlan, ...], view: IrAst) -> tuple[SplitPlan, ...]:
    """Every plan a safety proof licenses over ``view``, in cascade order."""
    return tuple(
        certified for plan in plans if (certified := _certified(plan, view)) is not None
    )


def split_model[M: IrNamedTuple](
    parse: ModelProduct,
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
    :param ask: The document, its fold, and the caller's ambiguity resolver.
    :param cores: 0 = auto, 1 = sequential (so: never split), N = that many.
    :param analysis: A language-equivalent structural view for derived grammars
        whose parse model intentionally elides quoted interiors or wrappers.
    :returns: The model, or ``None`` to parse sequentially.
    """
    # Settle the universal gates before deriving a plan. Reducer folds can
    # issue thousands of tiny SubRun parses; under the GIL every one has one
    # worker, and under AUTO a sub-2-chunk input cannot divide. Asking roles,
    # ownership and region safety for work that policy has already refused is
    # pure serial overhead on the caller's fold path.
    workers = doc_workers(cores)
    if workers < 2 or len(ask.text) < 2 * MIN_CHUNK:
        return None
    safe_plans = _safe_plans(_split_plans(grammar), analysis or grammar)
    with PoolLease(workers) as pool:
        windows = (
            _scan_windows(safe_plans[0].scanner, ask.text, workers, pool)
            if safe_plans
            else None
        )
        for plan in safe_plans:
            cuts = _cut_offsets(plan, ask.text, cores, pool, windows)
            if (
                cuts
                and (model := _split_parse(parse, plan, ask, cuts, pool)) is not None
            ):
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
            found.mark,
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
    parse: ModelProduct,
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
    chunks, leads = parsed
    moved = envelope_tails(chunks, found.shape, ask.fold) if found else None
    if found is None or moved is None:
        return None
    tails, trimmed = moved
    witness = unit_witness(plan.grammar, found.shape.unit) or ""
    rebuilt = [
        parse(plan.lead_grammar, tails[at] + lead + witness, ask.fold, ask.resolve)
        for at, lead in enumerate(leads)
    ]
    return stitch_envelope(trimmed, rebuilt, found.shape, ask.fold)
