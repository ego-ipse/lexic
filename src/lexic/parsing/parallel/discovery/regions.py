"""Regions — the bracketed runs of a document that are worth dividing.

A document's parallelism does not live where its grammar's start rule is.
A tokenizer file is a small header beside two enormous tables; a log is one
flat list. What both have in common is BRACKETED RUNS: a delimited region
holding many separated items, at whatever depth it happens to sit.

This module finds those runs by scanning once, and cuts each into pieces
that are documents in their own right — a piece wrapped in its OWN region's
brackets is a well-formed instance of the rule that region belongs to, so it
parses at the cost of its own text and nothing more. That is the difference
that decides whether splitting pays: wrapping a piece in the whole
document's envelope re-parses every sibling table with every piece.

This module owns only region discovery and balanced piece selection. Model
orchestration composes those facts elsewhere; the retired reduction stitch
does not live beside the analysis.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Iterator, Sequence
from functools import partial
from typing import NamedTuple

from lexic.ir import IrAst
from lexic.parsing.caches import memo
from lexic.parsing.parallel.discovery.interiors import (
    Site,
    Skip,
    hides,
    interiors,
    skip_delimited,
    skip_leads,
    stray_spellings,
)
from lexic.parsing.parallel.discovery.shapes import (
    edge_char,
    literal_char,
    rule_table,
)
from lexic.parsing.parallel.policy import MIN_PIECE
from lexic.parsing.parallel.pool import WorkPool
from lexic.parsing.parallel.roles import (
    BracketArm,
    bracket_arms,
    repeated_bodies,
    standing_pairs,
)


class Region(NamedTuple):
    """One bracketed run of separated items.

    :ivar opener: Offset of the bracket opening it.
    :ivar closer: Offset of the bracket closing it.
    :ivar rule: The rule a piece of it parses under (``object``, ``array``).
    :ivar marks: Offsets of the separators directly inside it.
    """

    opener: int
    closer: int
    rule: str
    marks: tuple[int, ...]

    @property
    def span(self) -> int:
        """How many characters the region covers."""
        return self.closer - self.opener


_PAIRS: dict[int, tuple[IrAst, dict[str, tuple[str, str]]]] = memo({})
"""Pair memo — id(grammar) → (grammar, pairs), pinned like the anchor memo."""


def pair_rules(grammar: IrAst) -> dict[str, tuple[str, str]]:
    """opener → ``(closer, rule)`` for every bracketing rule the scan reads exactly.

    A piece of a region parses under the rule whose arm spells that pair, so
    the split needs the RULE, not just the characters. A pair stands only
    while every site the scan reads spelling either character is a delimiter
    of a standing arm (:func:`~lexic.parsing.parallel.roles.standing_pairs`).
    """
    entry = _PAIRS.get(id(grammar))
    if entry is None:
        read = partial(literal_char, rule_map=rule_table(grammar))
        arms = bracket_arms(grammar, read, enclosing=False)
        pairs = list(dict.fromkeys((arm.opener, arm.closer) for arm in arms))
        out: dict[str, tuple[str, str]] = {}
        for opener, closer in standing_pairs(pairs, partial(_strays, grammar, arms)):
            rule = next(arm.rule for arm in arms if arm[:2] == (opener, closer))
            out.setdefault(opener, (closer, rule))
        entry = (grammar, out)
        _PAIRS[id(grammar)] = entry
    return entry[1]


def _strays(
    grammar: IrAst, arms: list[BracketArm], standing: list[tuple[str, str]]
) -> frozenset[str]:
    """The standing pairs' characters a scan-read site spells off their arms.

    An arm whose opener another pair already claims delimits nothing: the scan
    would close it on the other pair's closer.
    """
    first: dict[str, str] = {}
    for opener, closer in standing:
        first.setdefault(opener, closer)
    held: dict[str, set[Site]] = {char: set() for pair in standing for char in pair}
    for arm in arms:
        if first.get(arm.opener) == arm.closer:
            held[arm.opener].add((arm.rule, arm.arm, 0))
            held[arm.closer].add((arm.rule, arm.arm, arm.closes))
    watched = frozenset(held) | (separators(grammar) - set(first))
    return stray_spellings(grammar, watched, held)


def separators(grammar: IrAst) -> frozenset[str]:
    """The characters that separate a repetition's items.

    Derived, never named: the single character every arm of a repeated body
    begins with is what stands between one item and the next.
    """
    spells = partial(literal_char, rule_map=rule_table(grammar))
    found = (
        edge_char(r.body, 0, spells) for r in repeated_bodies(grammar, nested=True)
    )
    return frozenset(char for char in found if char is not None)


class Vocab(NamedTuple):
    """What the sweep watches for, and what each character means to it.

    :ivar pairs: opener → ``(closer, rule)`` for the tracked bracket pairs.
    :ivar closers: closer → every opener it closes, each once — two standing
        pairs may share one closer (``"(" … ")"`` and ``"[" … ")"``).
    :ivar marks: The separator characters.
    :ivar skips: lead → its :data:`Skip`, one table so a non-skip character
        pays one dict miss. A single-character fast path beside it was built
        and MEASURED in-process at 0.98x — twice, results exact — and
        reverted: the recorded +2.6% it was to recover does not reproduce
        in-process, so the split's second lookup was all cost.
    """

    pairs: dict[str, tuple[str, str]]
    closers: dict[str, str]
    marks: frozenset[str]
    skips: dict[str, Skip]

    @property
    def watched(self) -> set[str]:
        """Every character the sweep must find."""
        return set(self.pairs) | set(self.closers) | self.marks | set(self.skips)


class Roles(NamedTuple):
    """The whole vocabulary as ONE string, and what each position means.

    Every role table has between one and a handful of entries and all of them
    are keyed by ONE character — ``literal_char`` for the pairs and the marks,
    an interior's lead character for the skips — so the four tables concatenate
    into a single spelling and ``str.find`` classifies a character in one pass.
    Which ROLE it found is which section the index landed in, and the same
    index reads :attr:`names`, :attr:`closes` (or :attr:`skips`) for whatever
    that role needs.

    **No character holds two roles**, so a character is spelled once and its
    one position is its role: the openers key one table and the closers
    another, :func:`~lexic.parsing.parallel.roles.standing_pairs` drops a pair
    whose character also delimits another in the other role, the marks
    exclude every pair character (:func:`scan_vocabulary`), and a skip's lead
    is never a watched character. The sections are laid out skips, openers,
    closers, marks.

    This is not a micro-preference. Shared-dict membership in this loop does
    not scale across threads on this build — measured at 0.53x on sixteen
    threads against 7.64x for the same loop over private containers — and the
    walk consulted three such dicts per structural offset. Reading one string
    is also faster serially, so the change does not rest on that explanation
    holding.

    **A frame waits for its own closer.** An opener's frame carries the closer
    its pair ends on, read off :attr:`closes` at OPEN, and a closer closes the
    top frame when it is that character. So two pairs sharing one closer
    (``"(" … ")"`` and ``"[" … ")"``) each close their own frame: keyed by the
    closer alone, one opener would win and the other's frames never close.

    **Closers and marks share a section**, and no boundary separates them,
    because one test already does: a closer's name is non-empty and a mark's is
    ``""``, so a closer the top frame does not wait for is simply dropped.

    :ivar spelling: Every watched character, once: skips, openers, then
        closers and marks together. It is both the classification table and
        what a window sweeps, which is what makes ``spelling.find`` total over
        swept offsets — every offset a sweep reports holds a character of this
        string, so neither walk tests for ``-1``.
    :ivar skips: Parallel to the skip section, which starts at zero.
    :ivar names: Parallel to the WHOLE spelling — the bracket rule under an
        opener, the openers it closes under a closer, ``""`` under a mark, and
        ``""`` under the skip section, which is padded so the walk indexes by
        position and never subtracts.
    :ivar closes: Parallel to the whole spelling like :attr:`names` — the
        closer an opener's frame waits for, ``""`` everywhere else.
    :ivar n_skip: Where the opener section begins.
    :ivar n_open: Where the closers and marks begin.
    """

    spelling: str
    skips: tuple[Skip, ...]
    names: tuple[str, ...]
    closes: tuple[str, ...]
    n_skip: int
    n_open: int


type Frame = tuple[int, str, list[int], str]
"""One open bracket on the walk's stack: where, the closer it waits for, its
marks, its rule.

The rule travels ON the frame because the index that named it was already in
hand at OPEN time; re-deriving it at close would be the lookup this spelling
removes.
"""


def walk_roles(vocab: Vocab) -> Roles:
    """Spell a vocabulary for the walk, one section per role.

    Each section's characters and its values come from ONE iteration of the
    same mapping, so position ``i`` of the spelling and entry ``i`` of the
    values cannot disagree.
    """
    marks = "".join(vocab.marks)
    n_skip = len(vocab.skips)
    spelling = (
        "".join(vocab.skips) + "".join(vocab.pairs) + "".join(vocab.closers) + marks
    )
    return Roles(
        spelling=spelling,
        skips=tuple(vocab.skips.values()),
        names=(
            ("",) * n_skip  # the skip section, so `names` indexes by `pos`
            + tuple(rule for _closer, rule in vocab.pairs.values())
            + tuple(vocab.closers.values())
            + ("",) * len(marks)
        ),
        # `closer[0]` is the shared one-character object `spelling[pos]` also
        # hands out (CPython shares those below U+0100), so a close test is an
        # identity hit: measured 1-1.5% off the window walk at the mt seats.
        closes=(
            ("",) * n_skip
            + tuple(closer[0] for closer, _rule in vocab.pairs.values())
            + ("",) * (len(vocab.closers) + len(marks))
        ),
        n_skip=n_skip,
        n_open=n_skip + len(vocab.pairs),
    )


def scan_vocabulary(grammar: IrAst) -> Vocab:
    """What the scan watches for: bracket pairs, separators, interiors.

    A region is carried only when it can carry a watched character and its
    lead character carries no role of its own. Skipping a region that hides
    nothing costs a swept delimiter and a search per occurrence for no change
    in the answer, and a lead character with a second role could not be
    handed to the skip unconditionally the way the sweep does.
    """
    pairs = pair_rules(grammar)
    closers: dict[str, str] = {}
    for opener, (closer, _rule) in pairs.items():
        closers[closer] = closers.get(closer, "") + opener
    # No pair character is a mark. A standing pair's closer can still spell a
    # separator, but only at a site the scan never reads (an unreachable rule,
    # or inside an interior the walk skips): a READ separator site spelling it
    # is no delimiter of the pair's arm, so :func:`pair_rules` would have let
    # the pair fall. The mark role is therefore never met, and dropping it
    # leaves every closer with one role.
    marks = separators(grammar) - set(pairs) - set(closers)
    watched = frozenset(pairs) | frozenset(closers) | marks
    skips = tuple(
        region
        for region in interiors(grammar)
        if region.opening[0] not in watched and hides(grammar, region, watched)
    )
    return Vocab(pairs, closers, marks, skip_leads(skips))


def sweep_offsets(text: str, watched: set[str]) -> list[int]:
    """Every offset in ``text`` holding one of ``watched``, in order.

    One C-level ``str.find`` pass per character: a Python loop over every
    character of a 10 MB document is itself a second of the answer.
    """
    offsets: list[int] = []
    for char in watched:
        at = text.find(char)
        while at != -1:
            offsets.append(at)
            at = text.find(char, at + 1)
    offsets.sort()
    return offsets


def find(grammar: IrAst, text: str, min_span: int = 0) -> list[Region]:
    """Every bracketed run in ``text``, with the separators inside it.

    One C-level sweep per watched character, merged by sort, then a stack
    walk over the structural offsets alone — a Python loop over every
    character of a 10 MB document is itself a second of the answer. Opaque
    interiors are skipped whole, their delimiter matched in full so a lead
    character that opens nothing here stays an ordinary character. A separator
    is attributed to the bracket that most recently opened, which is what
    makes the answer depth-agnostic: the caller asks for the BIGGEST runs
    rather than for a chosen level.

    :param grammar: The grammar whose roles and interiors drive the scan.
    :param text: The document.
    :param min_span: Omit smaller regions at close time; callers scheduling
        work use this to avoid retaining runs that cannot clear their floor.
    :returns: The regions, in closing order.
    """
    vocab = scan_vocabulary(grammar)
    return walk_regions(
        text, sweep_offsets(text, vocab.watched), walk_roles(vocab), min_span
    )


def walk_regions(
    text: str, offsets: list[int], roles: Roles, min_span: int
) -> list[Region]:
    """The stack walk over the swept structural offsets.

    ONE ``find`` per structural character classifies it: which section of
    :attr:`Roles.spelling` the index lands in is the role, and the same index
    reads the value that role needs. See :class:`Roles` for why the tables are
    one string rather than four dicts, and why each character has one section.

    The tables are aliased into locals before the loop, deliberately: reading
    them off the record inside it measured 10-30% slower across the roster,
    18% on the grammar that walks the most offsets. One unpack of the record
    aliases them all, cheaper than a field read each.

    The opening bracket's rule is read at OPEN time, off the index the find
    already produced, and carried on the stack — so closing needs no lookup.
    The closer the frame waits for is read at OPEN time too, so a closer
    closes the top frame by comparing itself with it — read back off the
    spelling, where it is the same object as in :attr:`Roles.closes`.
    """
    spelling, skips, names, closes, n_skip, n_open = roles
    found: list[Region] = []
    stack: list[Frame] = []
    skip_to = 0
    for at in offsets:
        if at < skip_to:
            continue  # inside an opaque interior — never read
        pos = spelling.find(text[at])  # never -1: see Roles.spelling
        if pos < n_skip:
            skip_to = skip_delimited(text, at, skips[pos])
        elif pos < n_open:
            stack.append((at, closes[pos], [], names[pos]))
        elif stack and stack[-1][1] == spelling[pos]:
            if stack[-1][2] and at - stack[-1][0] >= min_span:
                found.append(_region(stack.pop(), at))
            else:
                stack.pop()
        elif stack and not names[pos]:
            stack[-1][2].append(at)  # a mark; a closer nothing wanted is dropped
    return found


def _region(frame: Frame, at: int) -> Region:
    """The region a popped frame closes at ``at``.

    Built only where one is kept: every close pops, and a frame holding no
    mark, or shorter than the floor, makes nothing — on deep nesting nearly
    every close — so the walks test that inline and pay no call for it.
    """
    return Region(frame[0], at, frame[3], tuple(frame[2]))


def _close(stack: list[Frame], found: list[Region], at: int, min_span: int) -> None:
    """Pop the opener ``at`` closes and keep its region, if it is one — the
    floor rule as the merge applies it, once per replayed event. The two walks
    test the same thing inline because they run it once per structural offset."""
    frame = stack.pop()
    if frame[2] and at - frame[0] >= min_span:
        found.append(_region(frame, at))


# ── the windowed find: the same answer, discovered in parallel ────────────

R_DONE, R_CLOSE, R_MARK, R_OPEN = "R", "C", "M", "O"
"""The four things a window can contribute to the merge.

A window walks its own slice with a stack that starts empty and is allowed to
UNDERFLOW, because the brackets enclosing its slice were opened in an earlier
one. Everything it can settle alone is settled; everything else becomes an
ordered event the merge replays against the one real stack.

``R_DONE`` is a region opened and closed inside the window — already final.
``R_CLOSE`` is a closer that underflowed, carrying its character, which the
merge compares with the closer its top frame waits for. ``R_MARK`` is a
separator at the underflow level. ``R_OPEN`` is an opener still standing at
the window's end, whose mark list later windows keep appending to.
"""


def par_find(
    grammar: IrAst,
    text: str,
    min_span: int,
    workers: int,
    pool: WorkPool | None = None,
) -> list[Region]:
    """:func:`find`, over ``workers`` windows — same regions, same order.

    **A grammar whose vocabulary carries an opaque interior takes the serial
    walk.** A window cannot know whether it begins inside one without a pass
    over everything before it, and that prepass measured 55.6% of the windowed
    find's wall clock on the grammar that needs it — more than the walk it
    enables, turning a win into a 17% regression. The condition is read off the
    vocabulary, so a grammar qualifies or not by what it derives; no grammar is
    named here, and one that grows an interior loses the window by itself.

    :param grammar: The grammar whose roles and interiors drive the scan.
    :param text: The document.
    :param min_span: Omit smaller regions at close time.
    :param workers: How many windows to divide the document into.
    :param pool: The pool the windows run on, or ``None`` to run every window
        on this thread. The answer may not depend on which — the differential
        runs without one.
    :returns: The regions, in closing order.
    """
    vocab = scan_vocabulary(grammar)
    roles = walk_roles(vocab)
    windows = max(1, min(workers, len(text)))
    if vocab.skips or windows < 2:
        return walk_regions(text, sweep_offsets(text, vocab.watched), roles, min_span)
    spans = window_bounds(len(text), windows)
    run = partial(_run_window, text, roles, min_span)
    chunks = pool.map(run, spans) if pool is not None else [run(s) for s in spans]
    return merge_windows(chunks, min_span)


def _run_window(
    text: str, roles: Roles, min_span: int, span: tuple[int, int]
) -> list[tuple]:
    """One window's replayable contribution.

    Module-level and bound with :func:`functools.partial` rather than closed
    over inside :func:`par_find`: the document, the roles and the floor are the
    same for every window, and the span is the only thing that varies.
    """
    return _window(text, span[0], span[1], roles, min_span)


def window_bounds(size: int, windows: int) -> list[tuple[int, int]]:
    """Arithmetic bounds covering ``[0, size)``, the last one taking the tail."""
    step = size // windows
    return [
        (k * step, (k + 1) * step if k < windows - 1 else size) for k in range(windows)
    ]


def _sweep_window(text: str, watched: str, lo: int, hi: int) -> list[int]:
    """:func:`sweep_offsets` restricted to ``[lo, hi)``.

    Sound because every watched spelling is ONE character, so no occurrence can
    straddle an arithmetic boundary and every offset belongs to exactly one
    window.

    Takes the DEDUPLICATED alphabet, never the classification spelling: a
    character that is both a closer and a separator stands in two sections of
    the spelling, and sweeping that would report every one of its offsets
    twice — which the serial sweep, over a set, never does.
    """
    offsets: list[int] = []
    for char in watched:
        at = text.find(char, lo, hi)
        while at != -1:
            offsets.append(at)
            at = text.find(char, at + 1, hi)
    offsets.sort()
    return offsets


def _window(text: str, lo: int, hi: int, roles: Roles, min_span: int) -> list[tuple]:
    """Walk ``[lo, hi)`` with a stack that may underflow, as ordered events.

    A mirror of :func:`walk_regions`, branch for branch and in the same order, with
    two differences: the stack starts empty and may go below its own floor, and
    what it cannot resolve alone becomes an event instead of being dropped.

    There is no skip branch. :func:`par_find` refuses to window a vocabulary
    that has one, so ``n_skip`` is zero here and the opener section starts at
    the first position.
    """
    spelling, _skips, names, closes, _n_skip, n_open = roles
    events: list[tuple] = []
    stack: list[Frame] = []
    for at in _sweep_window(text, spelling, lo, hi):
        pos = spelling.find(text[at])  # never -1: see Roles.spelling
        if pos < n_open:
            stack.append((at, closes[pos], [], names[pos]))
        elif stack and stack[-1][1] == spelling[pos]:
            if stack[-1][2] and at - stack[-1][0] >= min_span:
                events.append((R_DONE, at, _region(stack.pop(), at)))
            else:
                stack.pop()
        elif stack and not names[pos]:
            stack[-1][2].append(at)  # a mark; a closer nothing wanted is dropped
        elif not stack:
            events.append(
                (R_MARK, at) if not names[pos] else (R_CLOSE, at, spelling[pos])
            )
    # Already in document order, and the residual openers belong at the end:
    # the loop appends as it sweeps, which is ascending, and every frame still
    # on the stack opened before the window's last event and closes after it.
    events.extend((R_OPEN, frame[0], frame) for frame in stack)
    return events


def merge_windows(chunks: list[list[tuple]], min_span: int) -> list[Region]:
    """Replay every window's events against one stack, in document order.

    O(windows x depth): each window contributes at most its own residual depth
    in openers, and every other event is settled in constant time.

    Public because the replay IS the windowed find's correctness argument, and
    the differential that proves it has to be able to break it: a sabotage
    that cannot reach this cannot show the comparison would fail.
    """
    stack: list[Frame] = []
    found: list[Region] = []
    for events in chunks:
        for event in events:
            kind = event[0]
            if kind == R_DONE:
                found.append(event[2])
            elif kind == R_OPEN:
                stack.append(event[2])
            elif kind == R_CLOSE:
                if stack and stack[-1][1] == event[2]:
                    _close(stack, found, event[1], min_span)
            elif stack:  # R_MARK
                stack[-1][2].append(event[1])
    return found


type Starts = Callable[[int], int | None]
"""Where the piece after a cut at a mark starts, or ``None`` when the mark
cannot be cut at."""


type Around = Callable[[float, int, int], Iterator[int]]
"""Cuttable marks, asked for nearest first — what :func:`floor_cuts` reads:
``around(want, lo, hi)`` yields the marks in ``[lo, hi)``, nearest ``want``
first, the earlier on a tie. A divider holding its marks as a list hands
:func:`listed`; one that can find them where they are asked for need never
list the rest."""


def listed(marks: Sequence[int], want: float, lo: int, hi: int) -> Iterator[int]:
    """The ascending ``marks`` in ``[lo, hi)``, nearest ``want`` first, the
    earlier on a tie — an :data:`Around` over a list, by bisection. Read by
    index: two generators into :func:`nearest_first` cost 1.4–1.7× an ask."""
    first, end = bisect_left(marks, lo), bisect_left(marks, hi)
    right = bisect_left(marks, want, first, end)
    left = right - 1
    while left >= first or right < end:
        if right >= end or (
            left >= first and want - marks[left] <= marks[right] - want
        ):
            yield marks[left]
            left -= 1
        else:
            yield marks[right]
            right += 1


def nearest_first(down: Iterator[int], up: Iterator[int], want: float) -> Iterator[int]:
    """Offsets walking ``down`` from ``want`` and ``up`` from it, nearest it first."""
    before, after = next(down, -1), next(up, -1)
    while before >= 0 or after >= 0:
        if after < 0 or (before >= 0 and want - before <= after - want):
            at, before = before, next(down, -1)
        else:
            at, after = after, next(up, -1)
        yield at


type Cutting = tuple[Around, tuple[int, int], Starts, tuple[bool, int]]
"""One divider's question to :func:`floor_cuts`, asked at any worker count:
``(marks, span, starts, keeps)`` — the cuttable marks; the text being divided,
``(lo, hi)``; where the piece after a cut at a mark starts, or ``None`` where
that mark cannot be cut at; and whether the piece before a cut keeps its mark,
with how far past the mark it may then end (what lets the search skip the marks
too early to cut at unread). A plain tuple: it is built once per document on
the cut path."""


def floor_cuts(cutting: Cutting, workers: int) -> tuple[list[int], list[int]] | None:
    """The marks ``workers`` even shares of ``span`` are cut at, and where the
    piece after each starts — THE cut chooser every divider uses.

    Cut ``k`` snaps to the mark nearest ``k`` shares; only where that leaves
    the piece before it, or what is left after it, under
    :data:`~lexic.parsing.parallel.policy.MIN_PIECE` does the cut walk on to
    the nearest mark that does not. The next piece starts where ``starts``
    says, and the piece before ends there too if it keeps its mark, at the
    mark otherwise. So every piece holds ``MIN_PIECE``, and a caller need not
    check it again.

    :returns: ``(marks, starts)``, ascending, or ``None`` when no mark fits a cut.
    """
    lo, hi = cutting[1]
    cuts: list[int] = []
    begins: list[int] = []
    # The per-piece floor as one window per cut: the piece before must end at
    # `need` or later, and the rest from `room` on feed every piece left.
    need = lo + MIN_PIECE
    for k in range(1, workers):
        room = hi - (workers - k) * MIN_PIECE
        fit = _nearest_fit(cutting, lo + (hi - lo) * k / workers, need, room)
        if fit is None:
            return None
        cuts.append(fit[0])
        begins.append(fit[1])
        need = fit[1] + MIN_PIECE
    return cuts, begins


def _nearest_fit(
    cutting: Cutting, want: float, need: int, room: int
) -> tuple[int, int] | None:
    """The mark nearest ``want`` (the earlier on a tie) whose piece ends at
    ``need`` or later and whose next piece starts by ``room``, with that
    start — walked nearest first over the floor's window, the marks in
    ``[need - slack, room)``, so the first that fits is the one taken: usually
    the nearest of all."""
    around, _span, starts, (kept, slack) = cutting
    for at in around(want, need - slack, room):
        start = starts(at)
        if start is not None and start <= room and (start if kept else at) >= need:
            return at, start
    return None
