"""The top-down partition — which spans to divide so each piece is a worker's share.

A PARTITION takes a tree of divisible spans — each an opener and closer
around items separated at known offsets, the tree read from containment —
and a target of one worker's share of the text. It returns the spans to
divide and the separators to cut them at; :func:`units` renders every piece,
and the shell, with the stand-in of each divided span inside it.

Nothing here knows what a span's brackets are: the region scan is the one
supplier today (:mod:`~lexic.parsing.parallel.discovery.regions`), and any
plan that can state its spans this way can hand them to the same partition.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from typing import NamedTuple, Protocol

from lexic.parsing.parallel.policy import MIN_CHUNK


class Span(Protocol):
    """A divisible span: an opener and a closer around separated items.

    :ivar opener: Offset of the character opening it.
    :ivar closer: Offset of the character closing it.
    :ivar marks: Offsets of the separators directly inside it.
    """

    @property
    def opener(self) -> int:
        """Offset of the character opening it."""
        raise NotImplementedError

    @property
    def closer(self) -> int:
        """Offset of the character closing it."""
        raise NotImplementedError

    @property
    def marks(self) -> tuple[int, ...]:
        """Offsets of the separators directly inside it."""
        raise NotImplementedError

    @property
    def span(self) -> int:
        """How many characters it covers."""
        raise NotImplementedError


class Division[S: Span](NamedTuple):
    """A region :func:`partition` divided: the separator offsets between its
    runs. No cut is a region shipped whole, as one piece.

    The piece TEXTS are not held here: a piece carries the stand-ins of the
    divided regions inside it, which are chosen after the partition.
    """

    region: S
    cuts: tuple[int, ...]

    @property
    def bounds(self) -> list[int]:
        """Source bounds of its pieces: the interior, split after each cut."""
        return [
            self.region.opener + 1,
            *[cut + 1 for cut in self.cuts],
            self.region.closer,
        ]


class _Nest[S: Span](NamedTuple):
    """Each region's direct children, and the regions no other region holds."""

    children: dict[S, list[S]]
    top: list[S]


def _nest[S: Span](found: list[S]) -> _Nest[S]:
    """Nesting by one ordered pass: brackets nest, so a region's parent is the
    innermost earlier region still open at its opener."""
    children: dict[S, list[S]] = {}
    top: list[S] = []
    open_: list[S] = []
    for region in sorted(found, key=lambda r: (r.opener, -r.closer)):
        while open_ and open_[-1].closer < region.opener:
            open_.pop()
        (children.setdefault(open_[-1], []) if open_ else top).append(region)
        open_.append(region)
    return _Nest(children, top)


class _Partition[S: Span](NamedTuple):
    """One partition in progress: the piece size aimed at, the nesting, and
    the divisions made so far."""

    target: float
    nest: _Nest[S]
    out: list[Division[S]]


def partition[S: Span](text: str, found: list[S], workers: int) -> list[Division[S]]:
    """The regions to divide so each piece is about a ``workers``-th of the text.

    Top-down: a region's items pack into runs of ADJACENT items of at most
    ``len(text) / workers`` — each run one piece in the region's own brackets,
    so siblings that ship together come back already joined. An item larger
    than that whose value is a region is DESCENDED into and partitioned the
    same way; everything else ships whole, so only the regions on the path of
    an oversized item are divided — each of them, even one whose items make a
    single run, so a descended region is held by a PIECE, where the stitch
    finds it by item, not by walking; only a path region with under
    :data:`MIN_CHUNK` of its own text is left to its holder. The text outside every region
    is the shell; its largest regions ship as pieces of their own until what
    stays in it is no larger than one piece. Every run clears
    :data:`MIN_CHUNK`.

    :returns: The divided regions, in document order.
    """
    plan = _Partition(len(text) / workers, _nest(found), [])
    kept = len(text)
    for region in sorted(plan.nest.top, key=lambda r: -r.span):
        if kept <= plan.target:
            break
        left = _divide(plan, region)
        if left == region.span:
            plan.out.append(Division(region, ()))
            left = 0
        kept -= region.span - left
    pieces = sum(len(division.cuts) + 1 for division in plan.out)
    if pieces + (kept >= MIN_CHUNK) < 2:
        return []  # one unit of work: nothing runs beside it
    return sorted(plan.out, key=lambda division: division.region.opener)


def _divide[S: Span](plan: _Partition[S], region: S) -> int:
    """Partition ``region``; how much of its text stays with what holds it.

    ``0`` once it is divided. A region whose only change is a descended value
    is divided too — as one piece holding that value's stand-in — unless what
    is left of it is under :data:`MIN_CHUNK`: then its holder keeps that text,
    and finding the stand-in in so little costs less than a unit of its own.
    """
    if region.span <= plan.target:
        return region.span
    starts = [region.opener + 1, *[mark + 1 for mark in region.marks]]
    ends = [*region.marks, region.closer]
    sizes = [hi + 1 - lo for lo, hi in zip(starts, ends, strict=True)]
    whole = sum(sizes)
    kids = plan.nest.children.get(region, [])
    for at in [at for at, size in enumerate(sizes) if size > plan.target]:
        sizes[at] = _item(plan, kids, starts[at], ends[at])
    cuts = _runs(plan.target, sizes, region.marks)
    left = region.span - whole + sum(sizes)
    if cuts or MIN_CHUNK <= left < region.span:
        plan.out.append(Division(region, cuts))
        return 0
    return left


def _item[S: Span](plan: _Partition[S], kids: list[S], lo: int, hi: int) -> int:
    """An oversized item's weight in its region's runs: its text and the
    separator after it, less whatever of a descended value no longer travels
    with it."""
    size = hi + 1 - lo
    kid = next((k for k in kids if lo <= k.opener and k.closer < hi), None)
    if kid is None or kid.span <= plan.target:
        return size
    return size - kid.span + _divide(plan, kid)


def _runs(target: float, sizes: list[int], marks: tuple[int, ...]) -> tuple[int, ...]:
    """Separators between greedy runs of adjacent items of at most ``target``.

    A run is closed only once it clears :data:`MIN_CHUNK`, and a last run
    under it rejoins the one before, so no piece falls below the floor.
    """
    cuts: list[int] = []
    run = 0
    for at, size in enumerate(sizes):
        if run >= MIN_CHUNK and run + size > target:
            cuts.append(marks[at - 1])
            run = 0
        run += size
    if cuts and run < MIN_CHUNK:
        cuts.pop()
    return tuple(cuts)


def render[S: Span](
    text: str, window: tuple[int, int], regions: list[S], keep: list[str]
) -> str:
    """``text`` over ``window`` with each region's interior replaced.

    The owning brackets remain, so the replaced model's bracket fields survive
    the stitch exactly.

    :param window: The ``[lo, hi)`` span rendered.
    :param regions: Non-overlapping regions inside the window, in document order.
    :param keep: One replacement interior per region.
    """
    lo, hi = window
    out: list[str] = []
    at = lo
    for region, item in zip(regions, keep, strict=True):
        out.append(text[at : region.opener + 1])
        out.append(item)
        at = region.closer
    out.append(text[at:hi])
    return "".join(out)


class Unit(NamedTuple):
    """One text parsed as one task: a piece of a divided region, or the shell.

    :ivar owner: The division it is a piece of; ``-1`` for the shell.
    :ivar text: Its source, each held division's interior replaced.
    :ivar held: The divisions whose stand-ins it carries, in document order.
    :ivar items: For each held division, which of this piece's items holds
        it — so the stitch looks inside that one item, not the whole piece.
        The shell has no items: ``-1``.
    """

    owner: int
    text: str
    held: list[int]
    items: list[int]


def units[S: Span](
    text: str, divided: list[Division[S]], keep: list[str]
) -> list[Unit]:
    """Every division's pieces, then the shell — each carrying the stand-ins
    of the divisions directly inside it.

    A division is held by the piece of the innermost other division around
    it, or by the shell. A held region never straddles a cut: the cuts are its
    holder's own separators, and it sits inside one of that holder's items.

    :param divided: The divisions, in document order.
    :param keep: Each division's stand-in interior.
    """
    held: dict[tuple[int, int], list[tuple[int, int]]] = {}
    open_: list[int] = []
    for index, division in enumerate(divided):
        opener = division.region.opener
        while open_ and divided[open_[-1]].region.closer < opener:
            open_.pop()
        key, item = (
            _place(divided[open_[-1]], open_[-1], opener) if open_ else ((-1, 0), -1)
        )
        held.setdefault(key, []).append((index, item))
        open_.append(index)
    stubs = _Stubs(text, divided, keep)
    out = [
        unit for index in range(len(divided)) for unit in _pieces(stubs, index, held)
    ]
    top = held.get((-1, 0), [])
    whole = stubs.rendered((0, len(text)), top)
    out.append(Unit(-1, whole, [k for k, _item in top], [-1] * len(top)))
    return out


def _place[S: Span](
    holder: Division[S], at: int, opener: int
) -> tuple[tuple[int, int], int]:
    """Where the holder ``at`` keeps a region opening at ``opener``: its piece,
    and that piece's item — counted in the holder's separators from the
    piece's start."""
    bounds, marks = holder.bounds, holder.region.marks
    piece = bisect_right(bounds, opener) - 1
    item = bisect_left(marks, opener) - bisect_left(marks, bounds[piece])
    return (at, piece), item


class _Stubs[S: Span](NamedTuple):
    """The text, the divisions, and the stand-in each one leaves where it is
    held — everything a unit is rendered from."""

    text: str
    divided: list[Division[S]]
    keep: list[str]

    def rendered(self, window: tuple[int, int], inner: list[tuple[int, int]]) -> str:
        """``window`` with each held division's stand-in in place."""
        return render(
            self.text,
            window,
            [self.divided[k].region for k, _item in inner],
            [self.keep[k] for k, _item in inner],
        )


def _pieces[S: Span](
    stubs: _Stubs[S], index: int, held: dict[tuple[int, int], list[tuple[int, int]]]
) -> list[Unit]:
    """One division's pieces, each in the region's own brackets."""
    region, bounds = stubs.divided[index].region, stubs.divided[index].bounds
    open_char, close_char = stubs.text[region.opener], stubs.text[region.closer]
    last = len(bounds) - 2
    out: list[Unit] = []
    for piece in range(last + 1):
        inner = held.get((index, piece), [])
        window = (bounds[piece], bounds[piece + 1] - (1 if piece < last else 0))
        body = stubs.rendered(window, inner)
        kept, items = [k for k, _i in inner], [i for _k, i in inner]
        out.append(Unit(index, open_char + body + close_char, kept, items))
    return out
