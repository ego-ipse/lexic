"""Where the cuts go — one document's offsets, chosen under the policy floor.

A plan says which spellings bound a unit; this says which of their occurrences
a given document is actually cut at. The two are separate lifetimes: the plan
is settled once per grammar, the offsets once per document, and the floor is
what decides whether the second is worth asking at all.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterator

from lexic.parsing.parallel.discovery.scan import Scanner, Window, clustered
from lexic.parsing.parallel.plan.envelope import admits
from lexic.parsing.parallel.plan.split import SplitPlan, matched
from lexic.parsing.parallel.policy import MIN_CHUNK, MIN_SCAN, worker_count
from lexic.parsing.parallel.pool import WorkPool


def scan_windows(
    scanner: Scanner, text: str, workers: int, pool: WorkPool
) -> list[Window]:
    """Scan windows once for every separator plan of one grammar.

    A scanner carrying opaque regions walks instead: a window cannot know
    whether it begins inside one, and only the previous mark can say.

    How many windows is the SCAN's question, not the parse's: a window costs
    what a sweep of its own bytes costs, so :data:`~...policy.MIN_SCAN` bounds
    the count. Handing one worker per parse chunk put more time into dispatch
    than into scanning on every document a cheap grammar sees.
    """
    if scanner.opaque:
        return [scanner.walk(text)]
    windows = min(workers, max(1, len(text) // MIN_SCAN))
    if windows < 2:
        return [scanner.window(text, 0, len(text))]
    step = len(text) // windows
    bounds = [
        (k * step, (k + 1) * step if k < windows - 1 else len(text))
        for k in range(windows)
    ]
    return pool.map(lambda span: scanner.window(text, span[0], span[1]), bounds)


def scan_marks(
    plan: SplitPlan,
    text: str,
    workers: int,
    pool: WorkPool,
    windows: list[Window] | None = None,
) -> list[int]:
    """Depth-0 marks of this plan's spelling, over ``workers`` windows.

    Windows are arithmetic and each is scanned with no left context — a mark
    is structural at every occurrence, so a window needs nothing from its
    predecessor and the prefix-sum rebase recovers the absolute depths. One
    window IS the sequential scan. A spelling that overlaps itself is thinned
    to one boundary per run, after the rebase, so the answer does not depend
    on where the windows fell.

    The scanner reports every mark of the GRAMMAR; this plan keeps its own.
    Where every spelling is one character that selection is a membership test
    and nothing else: a one-character mark cannot overlap itself, so every
    width is 1 and :func:`~...discovery.scan.clustered` is the identity —
    which is that function's own stated contract, not a shortcut past it.
    """
    scanned = windows or scan_windows(plan.scanner, text, workers, pool)
    at_depth = plan.scanner.offsets(scanned, depth=0)
    if all(len(mark) == 1 for mark in plan.mark):
        return [at for at in at_depth if text[at] in plan.mark]
    widths = _widths(text, at_depth, plan.ordered)
    return clustered(sorted(widths), widths, plan.trailing)


def _widths(text: str, at_depth: list[int], ordered: tuple[str, ...]) -> dict[int, int]:
    """Each kept mark's matched spelling width, in document order."""
    return {at: len(hit) for at in at_depth if (hit := matched(text, at, ordered))}


def sole_mark(plan: SplitPlan) -> str:
    """The plan's one mark spelling, or ``""`` when it keys on a whole set.

    The proofs stated over a single mark — the announcing prefix, the separator
    exclusion, the agreed terminator — have no reading over a set, and say so
    by declining rather than by picking one of its members.
    """
    return next(iter(plan.mark)) if len(plan.mark) == 1 else ""


def cut_offsets(
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
        marks = scan_marks(plan, text, ceiling, pool, windows)
        if plan.bound is not None:
            # The unit emits its own mark, so a mark is a candidate rather than
            # a boundary: keep the ones a unit actually begins after. A
            # terminated unit starts immediately past its mark, with no
            # separator run to extend over — the envelope path's one difference.
            bound = sole_mark(plan)
            marks = [
                at for at in marks if admits(text, at + len(bound), plan.bound, bound)
            ]
    if plan.opening:
        # A proposal at offset zero would leave an empty first piece, which is
        # not a document; the tail needs no such guard, since a unit BEGINS at
        # the last proposal and its piece runs to the end.
        marks = [at for at in marks if at]
    elif plan.terminated and marks and after_mark(plan, text, marks[-1]) == len(text):
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
        previous = after_mark(plan, text, nearest)
    spans, _leads = cut_spans(plan, text, cuts)
    return (
        cuts
        if len(spans) == workers and min(hi - lo for lo, hi in spans) >= MIN_CHUNK
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
    # A terminated piece KEEPS its mark, so a candidate that close still
    # clears the floor; an OPENING mark belongs to the next piece and does not.
    owned = 0 if plan.opening else max((len(mark) for mark in plan.mark), default=1)
    lo = bisect_left(marks, previous + MIN_CHUNK - owned * int(terminated))
    hi = bisect_right(marks, len(text) - remaining * MIN_CHUNK - 1)
    for candidate in _nearby_marks(marks, want, lo, hi):
        after = after_mark(plan, text, candidate)
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
