"""Where the cuts go — one document's offsets, chosen under the policy floor.

A plan says which spellings bound a unit; this says which of their occurrences
a given document is actually cut at. The two are separate lifetimes: the plan
is settled once per grammar, the offsets once per document, and the floor is
what decides whether the second is worth asking at all.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterator
from functools import partial
from math import ceil
from typing import NamedTuple

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.regions import (
    Around,
    Cutting,
    floor_cuts,
    listed,
    nearest_first,
)
from lexic.parsing.parallel.discovery.scan import Scanner
from lexic.parsing.parallel.plan.envelope import admits
from lexic.parsing.parallel.plan.split import SplitPlan, matched
from lexic.parsing.parallel.policy import (
    MIN_SCAN,
    clears_floor,
    piece_count,
    worker_count,
)
from lexic.parsing.parallel.pool import WorkPool
from lexic.parsing.parallel.roles import Roles, Terminator, roles


def reads_a_sweep(plan: SplitPlan) -> bool:
    """Whether this plan's cuts are searched for by depth in the shared scan.

    Two shapes take their offsets elsewhere and must not put their marks into
    it. An ENVELOPE plan cuts on its own noise run
    (:meth:`~...plan.envelope.EnvelopePlan.cuts`) and never reads a depth at
    all — its mark is whitespace on the meta grammars, so searching for it
    would read a mark every few characters and discard every one. An OPAQUE
    plan WALKS the document unit by unit under its own region table, so its
    pass is not a depth search and is not interchangeable with one.
    """
    return plan.envelope is None and not plan.scanner.opaque


def shared_scanner(grammar: IrAst, plans: tuple[SplitPlan, ...]) -> Scanner | None:
    """One scanner sweeping exactly the spellings the certified plans cut at.

    A grammar derives every repetition separator and terminator it has, and the
    plan scanners carry that whole set — but a document is only ever cut at a
    mark some CERTIFIED plan keys on, so an occurrence of any other spelling is
    a position no cut can be proposed at. Reading it costs a ``find`` and a
    Python step per hit in every stretch a search reads, only to be discarded.
    A record grammar whose units are separated by spaces and terminated by
    three different closers scanned 3920 marks to select from 1680.

    The union is what makes ONE level serve every plan that reads one,
    proposals included: marks carry no depth, so merging two plans' spellings
    changes no depth count, and each plan still keeps its own
    (:class:`PlanMarks`). Pairs come from the grammar, because depth does not
    belong to any one plan.

    :param grammar: The codegen grammar the plans were derived from.
    :param plans: The certified plans, in cascade order.
    :returns: The shared scanner, or ``None`` when no certified plan reads a
        windowed sweep — see :func:`reads_a_sweep`.
    """
    marks = [plan.mark for plan in plans if reads_a_sweep(plan)]
    if not marks:
        return None
    wanted = frozenset[str]().union(*marks)
    return Scanner(Roles(roles(grammar).pairs, (), (Terminator(wanted, "", ""),)))


def sole_mark(plan: SplitPlan) -> str:
    """The plan's one mark spelling, or ``""`` when it keys on a whole set.

    The proofs stated over a single mark — the announcing prefix, the separator
    exclusion, the agreed terminator — have no reading over a set, and say so
    by declining rather than by picking one of its members.
    """
    return next(iter(plan.mark)) if len(plan.mark) == 1 else ""


STRETCH = 256
"""The first stretch a candidate search reads on each side of its target, in
characters; each further stretch on that side is twice the last."""

SPARSE = (4 * STRETCH, 16 * STRETCH)
"""How far into a document a plan's search reads before it calls the plan
sparse: past the first bound with no candidate at all, or past the second
without its first cuts' worth. A sparse plan is answered from the whole level
instead (:meth:`Level.whole`): searching it out stretch by stretch in Python
would walk the document alone, and once per plan."""


class Level:
    """One document's depth-0 marks under one scanner, shared by every plan
    that reads it.

    Read a stretch at a time where a search asks, from a depth counted at the
    stretch's start and remembered for the next; or, once any plan proves
    sparse, swept whole — in windows on the pool, each from its own counted
    depth — and listed for every plan after it. An opaque scanner's marks are
    the walk's, listed when first asked for: an envelope plan carries an opaque
    scanner and never asks.
    """

    def __init__(self, scanner: Scanner, text: str, pool: WorkPool | None = None):
        """Read ``text`` under ``scanner``; sweep it whole on ``pool``."""
        self.scanner, self.text, self.pool = scanner, text, pool
        self.known = ([0], [0])
        self.listed: list[int] | None = None

    def stretch(self, lo: int, hi: int) -> list[int]:
        """The depth-0 marks starting in ``[lo, hi)``, ascending."""
        if self.scanner.opaque:
            self.whole()
        whole = self.listed
        if whole is not None:
            return whole[bisect_left(whole, lo) : bisect_left(whole, hi)]
        return self.scanner.level(self.text, lo, hi, self.depth(lo))

    def whole(self) -> None:
        """List every depth-0 mark of the document, once.

        How many windows is the sweep's question, not the parse's: a window
        costs what a sweep of its own bytes costs, so :data:`~...policy.MIN_SCAN`
        bounds the count, and a pool that claims every CPU spares one.
        """
        if self.listed is not None:
            return
        text, scanner = self.text, self.scanner
        if scanner.opaque:
            self.listed = scanner.walk(text)
            return
        workers = piece_count(self.pool.workers) if self.pool is not None else 1
        windows = min(workers, max(1, len(text) // MIN_SCAN))
        step = len(text) // windows
        bounds = [k * step for k in range(windows)] + [len(text)]
        spans = [(lo, hi, self.depth(lo)) for lo, hi in zip(bounds, bounds[1:])]
        if self.pool is None or windows < 2:
            found = [scanner.level(text, lo, hi, base) for lo, hi, base in spans]
        else:
            found = self.pool.map(lambda span: scanner.level(text, *span), spans)
        self.listed = [at for part in found for at in part]

    def depth(self, at: int) -> int:
        """The absolute depth at ``at``: counted from the nearest depth already
        known on either side of it, and remembered."""
        offsets, depths = self.known
        index = bisect_right(offsets, at) - 1
        if offsets[index] == at:
            return depths[index]
        later = index + 1
        scanner, text = self.scanner, self.text
        if later < len(offsets) and offsets[later] - at < at - offsets[index]:
            depth = depths[later] - scanner.drift(text, at, offsets[later])
        else:
            depth = depths[index] + scanner.drift(text, offsets[index], at)
        offsets.insert(later, at)
        depths.insert(later, depth)
        return depth


class PlanMarks:
    """One plan's cut candidates in one document, found where they are asked for.

    A candidate is a depth-0 occurrence of a plan spelling, thinned to one per
    overlapping run, admitted by the plan's bound, and never the empty first or
    last piece a cut there would leave. The depth at a stretch's start is a
    count (:meth:`~...discovery.scan.Scanner.drift`), so a search reads only the
    stretches around its targets: choosing fifteen cuts no longer walks every
    mark in the document. Once its marks are listed — an envelope's own cuts,
    an opaque walk, a sparse plan's whole level — they are filtered once, and
    the candidates are read from that list by bisection.
    """

    def __init__(self, plan: SplitPlan, level: Level, held: list[int] | None) -> None:
        """Read ``level``'s depth-0 marks, or ``held`` when given."""
        self.plan, self.text, self.level, self.held = plan, level.text, level, held
        self.margin = max((len(mark) for mark in plan.mark), default=1)
        self.last: int | None = -1 if plan.terminated and not plan.opening else None
        self.ready: list[int] | None = None

    def around(self, want: float, lo: int, hi: int) -> Iterator[int]:
        """The candidates in ``[lo, hi)``, nearest ``want`` first, the earlier
        on a tie."""
        ready = self._listed()
        if ready is not None:
            yield from listed(ready, want, lo, hi)
            return
        lo, hi = max(lo, 0), min(hi, len(self.text))
        split = min(max(ceil(want), lo), hi)
        left, right = self._leftward(lo, split), self._rightward(split, hi)
        for at in nearest_first(left, right, want):
            if self._kept(at):
                yield at

    def found(self, count: int) -> int:
        """``count``, when the document holds that many candidates — read from
        its start until they are found or the plan proves sparse
        (:data:`SPARSE`) — else every candidate it holds, counted."""
        ready = self._listed()
        if ready is not None:
            return min(count, len(ready))
        found = 0
        for lo, hi in ((0, SPARSE[0]), SPARSE):
            for at in self._rightward(lo, min(hi, len(self.text))):
                found += self._kept(at)
                if found >= count:
                    return count
            if not found or hi >= len(self.text):
                break
        return self.counted()

    def counted(self) -> int:
        """Every candidate in the document, counted from the whole level."""
        self.level.whole()
        ready = self._listed()
        return len(ready) if ready is not None else 0

    def _listed(self) -> list[int] | None:
        """Every candidate, filtered once — when the marks are listed already.

        An envelope's own cuts need no plan filter, so they are taken as they
        stand: each is a ``str.find`` hit, so they ascend and every one stands
        inside the text. The rule that reads the whole document reads only its last
        candidate, so it costs one test rather than one per mark.
        """
        held, plan, text = self.held, self.plan, self.text
        if self.ready is not None or (held is None and self.level.listed is None):
            return self.ready
        if held is not None and plan.envelope is not None:
            ready = held[1:] if plan.opening and held and not held[0] else held
        else:
            ready = self._stretch(0, len(text))
        if self.last is not None:
            self.last = ready[-1] if ready else None
            if ready and after_mark(plan, text, ready[-1]) == len(text):
                ready = ready[:-1]
        self.ready = ready
        return ready

    def _kept(self, at: int) -> bool:
        """Whether ``at`` survives the one rule that reads the whole document:
        a terminated plan's last mark, when nothing but skip follows it."""
        if self.last == -1:
            self.last = next(self._leftward(0, len(self.text)), None)
        return not (
            at == self.last and after_mark(self.plan, self.text, at) == len(self.text)
        )

    def _rightward(self, lo: int, hi: int) -> Iterator[int]:
        """The raw candidates in ``[lo, hi)``, ascending, a stretch at a time."""
        size = STRETCH
        while lo < hi:
            yield from self._stretch(lo, min(lo + size, hi))
            lo, size = lo + size, 2 * size

    def _leftward(self, lo: int, hi: int) -> Iterator[int]:
        """The raw candidates in ``[lo, hi)``, descending, a stretch at a time."""
        size = STRETCH
        while lo < hi:
            yield from reversed(self._stretch(max(hi - size, lo), hi))
            hi, size = hi - size, 2 * size

    def _stretch(self, lo: int, hi: int) -> list[int]:
        """The raw candidates in ``[lo, hi)``: the plan's depth-0 marks, thinned
        and admitted. A run is thinned from its neighbours within one spelling's
        width, so the stretch is read ``margin`` past each end."""
        text, plan = self.text, self.plan
        wide_lo, wide_hi = max(lo - self.margin, 0), min(hi + self.margin, len(text))
        if self.held is not None:
            level = self.held[
                bisect_left(self.held, wide_lo) : bisect_left(self.held, wide_hi)
            ]
        else:
            level = self.level.stretch(wide_lo, wide_hi)
        if plan.envelope is not None:
            marks = [at for at in level if lo <= at < hi]
        elif self.margin == 1:
            marks = [at for at in level if lo <= at < hi and text[at] in plan.mark]
        else:
            marks = _thinned(text, plan, level, lo, hi)
        found = plan.bound
        if found is not None and plan.envelope is None:
            bound = sole_mark(plan)
            after = len(bound)
            marks = [at for at in marks if admits(text, at + after, found, bound)]
        return [at for at in marks if at] if plan.opening else marks


def _thinned(
    text: str, plan: SplitPlan, level: list[int], lo: int, hi: int
) -> list[int]:
    """The plan's matched marks in ``[lo, hi)``, one per overlapping run.

    A spelling that is its own border reads several times inside a run of its
    characters, and the grammar has one boundary there — at the run's end or at
    its start, whichever the owner's own edges settled. Marks overlap when the
    later starts inside the earlier's own matched width, so whether a mark
    opens (or closes) its run is read off its one neighbour, which ``level``
    holds whenever it reaches a spelling's width past ``[lo, hi)``.
    """
    widths = {at: len(hit) for at in level if (hit := matched(text, at, plan.ordered))}
    ordered = list(widths)
    kept: list[int] = []
    for index, at in enumerate(ordered):
        if not lo <= at < hi:
            continue
        if plan.trailing:
            later = ordered[index + 1] if index + 1 < len(ordered) else None
            if later is None or later - at >= widths[at]:
                kept.append(at)
            continue
        earlier = ordered[index - 1] if index else None
        if earlier is None or at - earlier >= widths[earlier]:
            kept.append(at)
    return kept


class Cuts(NamedTuple):
    """One document's chosen cuts, and the candidates they were chosen from.

    The two travel together because a proposal re-selects a failing cut among
    the same candidates, and asks for them where the failing cut stands.

    :ivar offsets: The chosen cut offsets, in document order; empty declines.
    :ivar marks: The candidates, asked for nearest first.
    """

    offsets: list[int]
    marks: Around


def cut_offsets(plan: SplitPlan, text: str, cores: int, level: Level) -> Cuts:
    """The chosen cut offsets — depth-0 marks of this plan's spelling, thinned.

    The worker CEILING is settled before anything is read: it depends only on
    the build, the core count and the input size, so a document that could
    never occupy two workers pays nothing to find that out.

    The candidates are searched for near each target rather than listed. Only
    a document holding fewer candidates than the ceiling's cuts is counted
    whole, since fewer marks bound the useful worker count.

    :param level: The document's depth-0 marks the candidates come from: the
        shared scanner's for a plan that reads a sweep, the plan's own scanner's
        (its walk, when opaque) otherwise.
    :returns: The chosen offsets and the candidates they came from.
    """
    ceiling = worker_count(len(text), len(text), cores)
    if ceiling < 2:
        return Cuts([], partial(listed, []))
    held = plan.envelope.cuts(text) if plan.envelope is not None else None
    marks = PlanMarks(plan, level, held)
    workers = piece_count(worker_count(len(text), marks.found(ceiling - 1), cores))
    # Listed by now, the candidates are read by bisection straight off the list.
    ready = marks.ready
    around = marks.around if ready is None else partial(listed, ready)
    cutting = _cutting(plan, text, around)
    while workers >= 2:
        cuts = _balanced_cuts(plan, text, workers, cutting)
        if cuts:
            return Cuts(cuts, around)
        workers -= 1
    return Cuts([], around)


def _cutting(plan: SplitPlan, text: str, marks: Around) -> Cutting:
    """This plan's question to the cut chooser: the next piece starts at
    :func:`after_mark`, and a terminated piece keeps its mark."""
    # A terminated piece KEEPS its mark, so a candidate that close still
    # clears the floor; an OPENING mark belongs to the next piece and does not.
    owned = 0 if plan.opening else max((len(mark) for mark in plan.mark), default=1)
    terminated = plan.terminated
    return (
        marks,
        (0, len(text)),
        partial(after_mark, plan, text),
        (terminated, owned * int(terminated)),
    )


def _balanced_cuts(
    plan: SplitPlan, text: str, workers: int, cutting: Cutting
) -> list[int]:
    """Marks nearest equal byte targets, if every actual span clears policy."""
    found = floor_cuts(cutting, workers)
    if found is None:
        return []
    cuts = found[0]
    spans, _leads = cut_spans(plan, text, cuts)
    return (
        cuts
        if len(spans) == workers and clears_floor(hi - lo for lo, hi in spans)
        else []
    )


def after_mark(plan: SplitPlan, text: str, mark: int) -> int:
    """First source offset owned by the piece after ``mark``."""
    if plan.envelope is not None:
        return plan.envelope.resumes(text, mark)
    if plan.opening:
        return mark  # the mark BEGINS the next unit, so the piece starts on it
    after = mark + len(matched(text, mark, plan.ordered))
    while after < len(text) and text[after] in plan.skip:
        after += 1
    return after


def cut_spans(plan: SplitPlan, text: str, cuts: list[int]) -> tuple[list, list[str]]:
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
        after = after_mark(plan, text, cut)
        # An envelope piece KEEPS the mark: a separator that begins before one
        # (a comment closed by it) would otherwise straddle the cut, and the
        # piece's own tail is what absorbs the run before the join takes it.
        kept = cut + len(matched(text, cut, plan.ordered))
        owned = kept if plan.envelope is not None else cut
        spans.append((prev, after if terminated else owned))
        leads.append("" if terminated else text[owned:after])
        prev = after
    spans.append((prev, len(text)))
    return spans, leads
