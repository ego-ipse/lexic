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
from functools import partial
from typing import NamedTuple

from lexic.ir import IrAlternation, IrAst, IrItem, IrRule, IrRuleRef
from lexic.parsing.parallel.discovery.interiors import (
    Skip,
    hides,
    interiors,
    skip_delimited,
    skip_leads,
)
from lexic.parsing.parallel.discovery.shapes import edge_char, literal_char, unbounded
from lexic.parsing.parallel.policy import MIN_CHUNK


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


def pair_rules(grammar: IrAst) -> dict[str, tuple[str, str]]:
    """opener → ``(closer, rule)`` for every derived bracketing rule.

    A piece of a region parses under the rule whose arm spells that pair, so
    the split needs the RULE, not just the characters.
    """
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    out: dict[str, tuple[str, str]] = {}
    for rule in grammar.rules:
        for arm in rule.body:
            items = tuple(arm)
            if len(items) < 3:
                continue
            opener = literal_char(items[0], rule_map)
            closers = [
                char
                for item in items[1:]
                if (char := literal_char(item, rule_map)) is not None
            ]
            if opener is None or not closers or closers[-1] == opener:
                continue
            out.setdefault(opener, (closers[-1], str(rule.name)))
    return out


def _repeated_bodies(
    items: tuple[IrItem, ...], rule_map: dict[str, IrRule]
) -> list[IrAlternation]:
    """Every unbounded body reachable from these items, nesting included.

    A repetition is often written inside another group — RFC json spells its
    member list ``[ member *( value-separator member ) ]`` — so a walk that
    reads only an arm's top-level items finds nothing that repeats.
    """
    out: list[IrAlternation] = []
    for item in items:
        atom = item.atom
        body = None
        if isinstance(atom, IrRuleRef):
            target = rule_map.get(str(atom))
            body = target.body if target is not None else None
        elif isinstance(atom, IrAlternation):
            body = atom
        if body is not None and unbounded(item):
            out.append(body)
        if isinstance(atom, IrAlternation):
            for arm in atom:
                out.extend(_repeated_bodies(tuple(arm), rule_map))
    return out


def separators(grammar: IrAst) -> frozenset[str]:
    """The characters that separate a repetition's items.

    Derived, never named: the single character every arm of a repeated body
    begins with is what stands between one item and the next.
    """
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    spells = partial(literal_char, rule_map=rule_map)
    found: set[str] = set()
    for rule in grammar.rules:
        for arm in rule.body:
            for body in _repeated_bodies(tuple(arm), rule_map):
                char = edge_char(body, 0, spells)
                if char is not None:
                    found.add(char)
    return frozenset(found)


class Vocab(NamedTuple):
    """What the sweep watches for, and what each character means to it.

    :ivar pairs: opener → ``(closer, rule)`` for the tracked bracket pairs.
    :ivar closers: closer → its opener.
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
    index reads :attr:`names` (or :attr:`skips`) for whatever that role needs.

    **The section order IS the branch precedence.** ``find`` returns the
    earliest match, and the sections are laid out skips, openers, closers,
    marks — the order the walk's branches used to be written in — so a
    character carrying two roles resolves exactly as it did when each table
    was tested in turn.

    This is not a micro-preference. Shared-dict membership in this loop does
    not scale across threads on this build — measured at 0.53x on sixteen
    threads against 7.64x for the same loop over private containers — and the
    walk consulted three such dicts per structural offset. Reading one string
    is also faster serially, so the change does not rest on that explanation
    holding.

    **Closers and marks share a section**, and no boundary separates them,
    because one test already does: a closer's value is its opener and a mark's
    is ``""``. An unmatched closer therefore falls through to the mark branch
    exactly as the elif chain let it, and the mark spelling is consulted only
    there — the one question a single find cannot answer.

    :ivar spelling: Every watched character: skips, openers, then closers and
        marks together.
    :ivar skips: Parallel to the skip section, which starts at zero.
    :ivar names: Parallel to the WHOLE spelling — the bracket rule under an
        opener, the owning opener under a closer, ``""`` under a mark, and
        ``""`` under the skip section, which is padded so the walk indexes by
        position and never subtracts.
    :ivar n_skip: Where the opener section begins.
    :ivar n_open: Where the closers and marks begin.
    :ivar mark_at: The mark characters, read only to decide whether an
        unmatched closer is also a separator.
    """

    spelling: str
    skips: tuple[Skip, ...]
    names: tuple[str, ...]
    n_skip: int
    n_open: int
    mark_at: str


type Frame = tuple[int, str, list[int], str]
"""One open bracket on the walk's stack: where, which, its marks, its rule.

The rule travels ON the frame because the index that named it was already in
hand at OPEN time; re-deriving it at close would be the lookup this spelling
removes.
"""


def _roles(vocab: Vocab) -> Roles:
    """Spell a vocabulary for the walk, sections in precedence order.

    Each section's characters and its values come from ONE iteration of the
    same mapping, so position ``i`` of the spelling and entry ``i`` of the
    values cannot disagree.
    """
    marks = "".join(vocab.marks)
    n_skip = len(vocab.skips)
    return Roles(
        spelling="".join(vocab.skips)
        + "".join(vocab.pairs)
        + "".join(vocab.closers)
        + marks,
        skips=tuple(vocab.skips.values()),
        names=(
            ("",) * n_skip  # the skip section, so `names` indexes by `pos`
            + tuple(rule for _closer, rule in vocab.pairs.values())
            + tuple(vocab.closers.values())
            + ("",) * len(marks)
        ),
        n_skip=n_skip,
        n_open=n_skip + len(vocab.pairs),
        mark_at=marks,
    )


def _vocabulary(grammar: IrAst) -> Vocab:
    """What the scan watches for: bracket pairs, separators, interiors.

    A region is carried only when it can carry a watched character and its
    lead character carries no role of its own. Skipping a region that hides
    nothing costs a swept delimiter and a search per occurrence for no change
    in the answer, and a lead character with a second role could not be
    handed to the skip unconditionally the way the sweep does.
    """
    pairs = pair_rules(grammar)
    marks = separators(grammar) - set(pairs)
    watched = frozenset(pairs) | {closer for closer, _rule in pairs.values()} | marks
    skips = tuple(
        region
        for region in interiors(grammar)
        if region.opening[0] not in watched and hides(grammar, region, watched)
    )
    closers = {closer: opener for opener, (closer, _rule) in pairs.items()}
    return Vocab(pairs, closers, marks, skip_leads(skips))


def _sweep(text: str, watched: set[str]) -> list[int]:
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
    vocab = _vocabulary(grammar)
    return _walk(text, _sweep(text, vocab.watched), _roles(vocab), min_span)


def _walk(text: str, offsets: list[int], roles: Roles, min_span: int) -> list[Region]:
    """The stack walk over the swept structural offsets.

    ONE ``find`` per structural character classifies it: which section of
    :attr:`Roles.spelling` the index lands in is the role, and the same index
    reads the value that role needs. See :class:`Roles` for why the tables are
    one string rather than four dicts, and why the section order reproduces the
    branch precedence the walk used to spell out.

    The tables are aliased into locals before the loop, deliberately: reading
    them off the record inside it measured 10-30% slower across the roster,
    18% on the grammar that walks the most offsets.

    The opening bracket's rule is read at OPEN time, off the index the find
    already produced, and carried on the stack — so closing needs no lookup.
    """
    spelling, skips, names = roles.spelling, roles.skips, roles.names
    n_skip, n_open = roles.n_skip, roles.n_open
    found: list[Region] = []
    stack: list[Frame] = []
    skip_to = 0
    for at in offsets:
        if at < skip_to:
            continue  # inside an opaque interior — never read
        char = text[at]
        pos = spelling.find(char)
        if pos < 0:
            continue  # swept for a character this vocabulary no longer claims
        if pos < n_skip:
            skip_to = skip_delimited(text, at, skips[pos])
        elif pos < n_open:
            stack.append((at, char, [], names[pos]))
        elif stack and stack[-1][1] == names[pos]:
            _close(stack, found, at, min_span)
        elif stack and (not names[pos] or char in roles.mark_at):
            stack[-1][2].append(at)  # a mark, or a closer nothing wanted
    return found


def _closed(stack: list[Frame], at: int, min_span: int) -> Region | None:
    """Pop the matched opener; the region it makes, or ``None`` if too small.

    Shed from the loop bodies because it runs once per REGION rather than once
    per structural offset: a walk's locals belong to the branches that run per
    character, and this one does not.
    """
    opener, _open_char, inside, rule = stack.pop()
    if inside and at - opener >= min_span:
        return Region(opener, at, rule, tuple(inside))
    return None


def _close(stack: list[Frame], found: list[Region], at: int, min_span: int) -> None:
    """Record the closed region, if it clears the floor.

    Appends rather than returning so :func:`_walk` spends no name on an outcome
    it only forwards.
    """
    region = _closed(stack, at, min_span)
    if region is not None:
        found.append(region)


# ── the windowed find: the same answer, discovered in parallel ────────────

R_DONE, R_CLOSE, R_MARK, R_OPEN = "R", "C", "M", "O"
"""The four things a window can contribute to the merge.

A window walks its own slice with a stack that starts empty and is allowed to
UNDERFLOW, because the brackets enclosing its slice were opened in an earlier
one. Everything it can settle alone is settled; everything else becomes an
ordered event the merge replays against the one real stack.

``R_DONE`` is a region opened and closed inside the window — already final.
``R_CLOSE`` is a closer that underflowed, carrying the opener it wants and
whether it is also a separator, which is the one thing the merge would
otherwise have to look up. ``R_MARK`` is a separator at the underflow level.
``R_OPEN`` is an opener still standing at the window's end, whose mark list
later windows keep appending to.
"""


def par_find(
    grammar: IrAst, text: str, min_span: int, workers: int, pool=None
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
    :param pool: A pool exposing ``map``, or ``None`` to run every window on
        this thread. The answer may not depend on which — the differential
        runs without one.
    :returns: The regions, in closing order.
    """
    vocab = _vocabulary(grammar)
    roles = _roles(vocab)
    windows = max(1, min(workers, len(text)))
    if vocab.skips or windows < 2:
        return _walk(text, _sweep(text, vocab.watched), roles, min_span)
    spans = _bounds(len(text), windows)

    def run(span: tuple[int, int]) -> list[tuple]:
        """One window's replayable contribution."""
        return _window(text, span[0], span[1], roles, min_span)

    chunks = pool.map(run, spans) if pool is not None else [run(s) for s in spans]
    return merge_windows(chunks, min_span)


def _bounds(size: int, windows: int) -> list[tuple[int, int]]:
    """Arithmetic bounds covering ``[0, size)``, the last one taking the tail."""
    step = size // windows
    return [
        (k * step, (k + 1) * step if k < windows - 1 else size) for k in range(windows)
    ]


def _sweep_window(text: str, spelling: str, lo: int, hi: int) -> list[int]:
    """:func:`_sweep` restricted to ``[lo, hi)``.

    Sound because every watched spelling is ONE character, so no occurrence can
    straddle an arithmetic boundary and every offset belongs to exactly one
    window.
    """
    offsets: list[int] = []
    for char in spelling:
        at = text.find(char, lo, hi)
        while at != -1:
            offsets.append(at)
            at = text.find(char, at + 1, hi)
    offsets.sort()
    return offsets


def _window(text: str, lo: int, hi: int, roles: Roles, min_span: int) -> list[tuple]:
    """Walk ``[lo, hi)`` with a stack that may underflow, as ordered events.

    A mirror of :func:`_walk`, branch for branch and in the same order, with
    two differences: the stack starts empty and may go below its own floor, and
    what it cannot resolve alone becomes an event instead of being dropped.

    There is no skip branch. :func:`par_find` refuses to window a vocabulary
    that has one, so ``n_skip`` is zero here and the opener section starts at
    the first position.
    """
    spelling, names, n_open = roles.spelling, roles.names, roles.n_open
    events: list[tuple] = []
    stack: list[Frame] = []
    for at in _sweep_window(text, spelling, lo, hi):
        char = text[at]
        pos = spelling.find(char)
        if pos < 0:
            continue  # swept for a character this vocabulary no longer claims
        if pos < n_open:
            stack.append((at, char, [], names[pos]))
        elif stack and stack[-1][1] == names[pos]:
            region = _closed(stack, at, min_span)
            if region is not None:
                events.append((R_DONE, at, region))
        elif stack and (not names[pos] or char in roles.mark_at):
            stack[-1][2].append(at)  # a mark, or a closer nothing wanted
        elif not stack:
            events.append(
                (R_MARK, at)
                if not names[pos]
                else (R_CLOSE, at, names[pos], char in roles.mark_at)
            )
    events.extend((R_OPEN, frame[0], frame) for frame in stack)
    events.sort(key=_at_of)
    return events


def _at_of(event: tuple) -> int:
    """An event's document offset.

    Every event carries it second, and a closed region carries its CLOSER —
    which is what orders the serial walk's answer, so replaying in this order
    reproduces that order rather than approximating it.
    """
    return event[1]


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
                elif stack and event[3]:
                    stack[-1][2].append(event[1])
            elif stack:  # R_MARK
                stack[-1][2].append(event[1])
    return found


def nearest_mark(marks: tuple[int, ...], want: float) -> int:
    """The mark closest to ``want`` — cuts aim at positions, not at counts."""
    at = bisect_left(marks, want)
    if at == 0:
        return marks[0]
    if at == len(marks):
        return marks[-1]
    before, after = marks[at - 1], marks[at]
    return before if want - before <= after - want else after


def piece_marks(region: Region, workers: int) -> list[int]:
    """The separator offsets :func:`pieces` removes from ``region``.

    Kept as a named result because the model stitch must rebuild each removed
    separator under the region's own grammar. Re-deriving the marks from the
    piece strings would guess at source extent when the same text repeats.

    :param region: The run being divided.
    :param workers: How many balanced pieces are wanted.
    :returns: Distinct separator offsets, in document order.
    """
    lo, hi = region.opener + 1, region.closer
    target = (hi - lo) / workers
    cuts: list[int] = []
    for k in range(1, workers):
        nearest = nearest_mark(region.marks, lo + k * target)
        if nearest not in cuts:
            cuts.append(nearest)
    return cuts


def pieces(text: str, region: Region, workers: int) -> list[str] | None:
    """``region`` cut into ``workers`` self-contained pieces, or ``None``.

    Each piece carries only its OWN brackets, so it costs its own text —
    the point of cutting regions rather than wrapping the document. Cuts aim
    at equal byte positions and take the nearest separator, because dividing
    the separator COUNT divides the work only when they are evenly spread.

    :param text: The document.
    :param region: The run to cut.
    :param workers: How many pieces are wanted.
    :returns: The pieces, or ``None`` when the run will not divide.
    """
    bounds = _piece_bounds(region, workers)
    return _piece_texts(text, region, bounds) if bounds is not None else None


def _piece_bounds(region: Region, workers: int) -> list[int] | None:
    """Source bounds for balanced pieces, without copying their text."""
    lo, hi = region.opener + 1, region.closer
    target = (hi - lo) / workers
    cuts = piece_marks(region, workers)
    if not cuts:
        return None
    bounds = [lo, *[cut + 1 for cut in cuts], hi]
    if max(bounds[i + 1] - bounds[i] for i in range(len(bounds) - 1)) > 2 * target:
        return None
    return bounds


def _piece_texts(text: str, region: Region, bounds: list[int]) -> list[str]:
    """Materialize one accepted bounds plan exactly once."""
    open_char, close_char = text[region.opener], text[region.closer]
    return [
        open_char
        + text[bounds[i] : bounds[i + 1] - (1 if i + 2 < len(bounds) else 0)]
        + close_char
        for i in range(len(bounds) - 1)
    ]


def stub(text: str, region: Region, nth: int = 0) -> str:
    """The region's ``nth`` item, used as its distinct shell stand-in.

    Different regions use different item indices so equal first entries do not
    route to the same shell node. The index is clamped; equality plus exact
    items-node class is still checked later, and an unresolved collision makes
    the split decline.

    :param text: The complete document.
    :param region: The run whose one item should remain.
    :param nth: The item index, clamped to the run's final item.
    :returns: The raw item span, without the region's brackets.
    """
    at = min(nth, len(region.marks))
    start = region.opener + 1 if at == 0 else region.marks[at - 1] + 1
    end = region.marks[at] if at < len(region.marks) else region.closer
    return text[start:end]


def shell(text: str, regions: list[Region], keep: list[str]) -> str:
    """Replace each divided interior by its one-item stand-in.

    The owning brackets remain in the shell. Model orchestration replaces only
    the parsed items child, so those bracket fields survive the stitch exactly.

    :param text: The complete document.
    :param regions: Non-overlapping divided runs, in document order.
    :param keep: One replacement interior per region.
    :returns: The small document parsed once to provide the outer model shell.
    """
    out: list[str] = []
    at = 0
    for region, item in zip(regions, keep, strict=True):
        out.append(text[at : region.opener + 1])
        out.append(item)
        at = region.closer
    out.append(text[at:])
    return "".join(out)


def choose(
    text: str, found: list[Region], workers: int
) -> list[tuple[Region, list[str]]]:
    """The biggest runs that actually divide, and their pieces.

    A document's outermost bracket contains every other, so size alone would
    divide the same text twice — and worse, a big run that CANNOT divide
    (a tokenizer file's top level is eight members, two of them enormous)
    would claim the territory and block the runs inside it that can. So a
    region takes its span only if its pieces come out balanced; otherwise it
    steps aside and its children are considered on their own.

    ``workers`` is a ceiling, not an exact demand. Each selected run uses the
    largest count it can feed at least :data:`MIN_CHUNK`, while the shared pool
    still caps aggregate concurrency. This keeps useful four-way work when a
    caller happens to have eight cores.
    """
    candidates: list[tuple[Region, list[str]]] = []
    for region in sorted(found, key=lambda r: -r.span):
        capacity = min(workers, region.span // MIN_CHUNK)
        if capacity < 2:
            continue
        for count in range(capacity, 1, -1):
            bounds = _piece_bounds(region, count)
            # Span capacity is only an upper bound. Sparse outer containers
            # can leave one nearly empty piece and one piece holding the whole
            # nested payload; accepting that blocks the balanced child region
            # and repeats its work in joints and the shell. Every ACTUAL owner
            # must clear the already measured per-worker floor.
            if (
                bounds is not None
                and min(bounds[i + 1] - bounds[i] + 1 for i in range(len(bounds) - 1))
                >= MIN_CHUNK
            ):
                candidates.append((region, _piece_texts(text, region, bounds)))
                break
    # Prefer the ownership plan that fills more runners. Span breaks ties, but
    # cannot let a three-way outer container suppress an eight-way child.
    picked: list[tuple[Region, list[str]]] = []
    for region, parts in sorted(
        candidates, key=lambda entry: (-len(entry[1]), -entry[0].span)
    ):
        if any(
            region.opener < other.closer and other.opener < region.closer
            for other, _parts in picked
        ):
            continue
        picked.append((region, parts))
    return sorted(picked, key=lambda entry: entry[0].opener)
