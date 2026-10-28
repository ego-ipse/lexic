"""The live set — the readings a boundary carries forward, pruned, merged and ranked.

A both-viable boundary in the live drive is settled by carrying every way it can
go forward at once, as a flat set of READINGS (:class:`Strand`): each a side
(a structural copy of the live stack with the boundary decided, :mod:`.sides`)
and the path of decisions that made it. A boundary met INSIDE a reading's drive does not nest a
verdict of its own and is not guessed: the reading SPLITS (:class:`Split`), one
child per way that boundary can go, built where it stood. So nothing in a set
guesses, and every death and every convergence in it is certain.

The set settles its boundary by three rules, each the answer the gated engine
gives:

- **a reading that dies is pruned** — it derives nothing;
- **readings that meet merge** — at one position, in one control state, with
  the same sub-runs still to settle, they share their whole future. Equal values
  keep one; different values are ranked by the decider at the split where they
  parted, on ledgers carried through every split since (:class:`Level`); a tie
  the decider does not separate is the ambiguity it is, and forks;
- **the boundary is decided** once every survivor descends from one of its
  ways, and the live drive goes on from there.

Readings advance in step: the ones furthest behind are driven to where the next
one stands, so readings that can meet do, the smallest way's first, and a step
ends once one way is left. At a loop boundary the reading AHEAD — the one that
took an iteration — leads one step first, so a take that dies a character
later costs the stop nothing.

What a set pays is what it needs. Ledgers, which only a rank reads, are kept
once a meeting has needed one (:class:`Unrecorded`). And a decided set's
survivors are the live parse's own continuation, so the splits they all came
through the same way are the boundaries the live drive meets next, already
answered (:func:`planned`).

The set is bounded, at :data:`SET_MAX` readings, :data:`SET_STEPS` steps and
:data:`~...admission.NESTING_DEPTH` splits. Past any of them it raises a
:class:`ProbeFork` that says so, and the gated engine decides: the one place a
boundary is left undecided.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.admission import (
    NESTING_DEPTH,
    Side,
    control_signature,
    forks_deep,
    pending_values,
    value_shape,
)
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel.verdicts.sides import PENDING, UNSEEN, Sides

__all__ = [
    "FORKED",
    "LEAD_STEP",
    "SET_MAX",
    "SET_STEPS",
    "STEP",
    "STOP_FORCED",
    "TAKE",
    "Level",
    "LiveSet",
    "Strand",
    "Split",
    "Unrecorded",
    "meeting",
    "planned",
    "ranked_level",
    "split_children",
]

TAKE, STOP_FORCED, FORKED = 0, 1, 2
"""A both-viable boundary's resolutions, as a rank answers them too: keep the
later way, keep the earlier, or a tie the decider does not separate."""

SET_MAX = 16
"""Most readings a set holds. A split past it is the bound: the boundary forks.
A rule that carves a run many ways (``[a]* "a"``) grows its set with the run:
measured, ``;aaaa!`` under ``end ::= [a;] | [a]* "a"`` peaks at 9 readings and
a run of six at 13, both rejected here; a longer one is the gated engine's."""

SET_STEPS = 128
"""Most steps a set takes before its boundary is decided. Past it: the bound."""

STEP = 8
"""Characters every reading advances by when they all stand at one position in
different control states — small, since a meeting is usually one element off."""

LEAD_STEP = 2
"""Characters the reading ahead steps first at a loop boundary, to see it die."""


class Split(BaseException):
    """A both-viable boundary inside a reading: the reading is replaced by its
    children, built where it stood.

    A :class:`BaseException`, so no handler between the boundary and the set
    reads it as a failure: it passes every ``except`` on its way out, and every
    ``finally`` restores what it holds.

    :ivar children: One side per way the boundary can go, in the decider's order.
    :ivar stack: The stack the split was taken on, as it stood.
    :ivar pos: Where the boundary stands.
    :ivar key: The boundary's control state and its number of ways.
    """

    def __init__(
        self,
        children: list[Side],
        stack: list[Frame[Any]],
        pos: int,
        key: tuple[Any, ...] = (),
    ) -> None:
        """Hold the children and where they were split from."""
        super().__init__(f"live set: split at {pos}")
        self.children = children
        self.stack = stack
        self.pos = pos
        self.key = key


class Unrecorded(Exception):
    """Two readings met with different values, and their sides keep no
    ledgers to rank them by: the set starts over keeping them."""


class Level(NamedTuple):
    """One split a reading came through, and the frames of it that completed.

    :ivar stack: The stack the split was taken on — what a rank there reads.
    :ivar pos: Where the boundary stood.
    :ivar done: Each of the split's copied frames that completed before a later
        split, by depth: where it completed, and its copy.
    :ivar key: The split's boundary: its control state and number of ways.
    """

    stack: list[Frame[Any]]
    pos: int
    done: dict[int, tuple[int, Frame[Any]]]
    key: tuple[Any, ...] = ()


class Strand(NamedTuple):
    """One reading of the set: a way its boundary can go, as far as it has
    been driven.

    :ivar side: The reading's side, keeping its ledger.
    :ivar path: The child taken at each split, the set's own boundary first.
    :ivar forks: That child's own step at each split (``Side[7]``).
    :ivar levels: The splits it came through, the set's own first.
    """

    side: Side
    path: tuple[int, ...]
    forks: tuple[tuple[int, int] | tuple[()], ...]
    levels: tuple[Level, ...]


class LiveSet[Carry](Sides[Carry]):
    """The set driver, hosted for :class:`~.verdicts.Verdicts` to inherit; the
    rank it reads is declared here, beside the lane it is asked through."""

    __slots__ = ()

    pos: int
    stack: list[Frame[Carry]]

    def _rank(self, stop: Side, take: Side) -> int:
        """Provided by ``Verdicts`` — two sides keeping ledgers, ranked."""
        raise NotImplementedError

    def _recording(self) -> bool:
        """Whether the reading being driven keeps a ledger — and so its split's
        children must, for a rank to read them through it."""
        side = self._caches.side
        return side is not None and side[5] is not None

    def _split(self, children: list[Side], pos: int) -> Split:
        """The signal a boundary inside a reading raises, its children built.

        :raises ProbeFork: When the reading already came through
            :data:`~...admission.NESTING_DEPTH` splits — the bound.
        """
        if forks_deep(self.stack) >= NESTING_DEPTH:
            raise ProbeFork(
                f"live set at {pos}: a reading split {NESTING_DEPTH} times;"
                " the gated engine decides",
                pos,
            )
        key = (*control_signature(self.stack, pos), len(children))
        return Split(children, list(self.stack), pos, key)

    def _decide(
        self, roots: Sequence[Callable[[bool], Side]], ahead_first: bool
    ) -> int:
        """The way the boundary goes: an index into ``roots``. A way is left
        whichever die, since a step stops as soon as one is (:meth:`_driven`):
        if that one dies too, the live drive finds out.

        A set runs first keeping no ledgers, which only a rank reads: a set
        decided by deaths and agreements never pays for them. Where two
        readings meet with different values it starts over keeping them —
        the same set, so the same answer, now rankable — and every later set
        of the parse keeps them from the start.

        :param roots: Each way the boundary can go, as a builder of its side,
            keeping a ledger or not.
        :param ahead_first: A loop boundary, whose reading ahead steps first.
        :raises ProbeFork: On a decider tie, an undecidable reading, or the bound.
        """
        scope = self._caches.scope
        kept = scope.answered(self.stack, self.pos, len(roots))
        if kept >= 0:
            return kept
        level = Level(self.stack, self.pos, {})
        if scope.ranks:
            return self._settled(roots, ahead_first, level, True)
        try:
            return self._settled(roots, ahead_first, level, False)
        except Unrecorded:
            scope.ranks = True
            return self._settled(roots, ahead_first, level, True)

    def _settled(
        self,
        roots: Sequence[Callable[[bool], Side]],
        ahead_first: bool,
        level: Level,
        record: bool,
    ) -> int:
        """The set itself, from its own split ``level``, its sides keeping
        ledgers or not; a decided set leaves the live drive the choices its
        survivors share past it (:func:`planned`).

        :raises Unrecorded: When a meeting needs a rank and ``record`` is off.
        """
        readings = [
            Strand(side, (j,), (side[7],), (level,))
            for j, side in enumerate(build(record) for build in roots)
        ]
        for _step in range(SET_STEPS):
            readings = self._merged(readings)
            ways = {reading.path[0] for reading in readings}
            if len(ways) <= 1:
                self._caches.scope.answers = planned(readings)
                return next(iter(ways))
            readings = self._stepped(readings, ahead_first and not _step)
            if len(readings) > SET_MAX:
                raise ProbeFork(
                    f"live set at {self.pos}: {len(readings)} readings exceed"
                    f" {SET_MAX}; the gated engine decides",
                    self.pos,
                )
        raise ProbeFork(
            f"live set at {self.pos}: undecided after {SET_STEPS} steps;"
            " the gated engine decides",
            self.pos,
        )

    def _stepped(self, readings: list[Strand], ahead_first: bool) -> list[Strand]:
        """One step: the readings furthest behind driven to where the next one
        stands (all of them a :data:`STEP` on where they stand together); at a
        loop boundary, the readings ahead a :data:`LEAD_STEP` first."""
        places = sorted({reading.side[1] for reading in readings})
        if ahead_first and len(places) > 1:
            lead = places[-1]
            readings = self._driven(readings, lambda at: at == lead, lead + LEAD_STEP)
            if len({reading.path[0] for reading in readings}) <= 1:
                return readings
        places = sorted({reading.side[1] for reading in readings})
        behind = places[0]
        target = places[1] if len(places) > 1 else behind + STEP
        return self._driven(readings, lambda at: at == behind, target)

    def _driven(
        self, readings: list[Strand], chosen: Callable[[int], bool], target: int
    ) -> list[Strand]:
        """``readings`` with each one standing where ``chosen`` holds driven to
        ``target``: advanced, pruned where it dies, or replaced by its children
        where it splits.

        The readings of the smallest ways are driven first, and the step ends
        as soon as one way is left: a way's last reading dying decides the
        set, and the rest need not move for it. Readings keep their order.
        """
        ways: dict[int, int] = {}
        for reading in readings:
            ways[reading.path[0]] = ways.get(reading.path[0], 0) + 1
        live = len(ways)
        chosen_ones = [
            index
            for index, reading in enumerate(readings)
            if chosen(reading.side[1]) and reading.side[0]
        ]
        chosen_ones.sort(key=lambda index: ways[readings[index].path[0]])
        results: list[list[Strand]] = [[reading] for reading in readings]
        for index in chosen_ones:
            if live <= 1:
                break
            reading = readings[index]
            try:
                driven = self._advance(reading.side, target)
            except Split as split:
                results[index] = split_children(reading, split)
                continue
            if driven is None:
                results[index] = []
                ways[reading.path[0]] -= 1
                live -= not ways[reading.path[0]]
            else:
                results[index] = [
                    Strand(driven, reading.path, reading.forks, reading.levels)
                ]
        return [reading for result in results for reading in result]

    def _merged(self, readings: list[Strand]) -> list[Strand]:
        """``readings`` with every two that meet merged into one. A cheap key
        goes first — where it stands, the sub-runs it still has to settle, its
        depth and top frame — and only readings sharing it pay the full
        control state (:func:`meeting`)."""
        if len({reading.side[1] for reading in readings}) == len(readings):
            return readings  # no two stand together
        cheap: dict[tuple[Any, ...], int] = {}
        for reading in readings:
            near = _near(reading.side)
            cheap[near] = cheap.get(near, 0) + 1
        groups: dict[Any, list[Strand]] = {}
        for index, reading in enumerate(readings):
            alone = cheap[_near(reading.side)] == 1
            key = index if alone else meeting(reading.side)
            groups.setdefault(key, []).append(reading)
        out: list[Strand] = []
        for group in groups.values():
            kept = group[0]
            for other in group[1:]:
                kept = self._met(kept, other)
            out.append(kept)
        return out

    def _met(self, one: Strand, other: Strand) -> Strand:
        """Two readings that met, as one: equal values keep the later way (the
        take); different values are ranked at the split where they parted —
        the first whose choice both did not roll back (:func:`ranked_level`).

        :raises ProbeFork: On a tie the decider does not separate.
        """
        at = _parted(one, other)
        stop, take = (one, other) if one.path[at] < other.path[at] else (other, one)
        shape = value_shape(stop.levels[at].stack)
        if same_value(_built(stop.side, shape), _built(take.side, shape)):
            return take
        if stop.side[5] is None or take.side[5] is None:
            raise Unrecorded
        at = ranked_level(stop, take, at)
        if at < 0:
            raise ProbeFork(
                f"live set at {self.pos}: two readings parted only where they"
                " cannot be ranked; the gated engine decides",
                self.pos,
            )
        if stop.path[at] > take.path[at]:
            stop, take = take, stop
        level = stop.levels[at]
        saved_stack, saved_pos = self.stack, self.pos
        self.stack, self.pos = level.stack, level.pos
        try:
            verdict = self._rank(_at(stop, at), _at(take, at))
        finally:
            self.stack, self.pos = saved_stack, saved_pos
        if verdict == FORKED:
            raise ProbeFork(
                f"live set at {level.pos}: two readings the decider does not"
                " separate; the gated engine decides",
                level.pos,
            )
        return take if verdict == TAKE else stop


def planned(survivors: list[Strand]) -> list[tuple[tuple[Any, ...], int]]:
    """The choices every survivor of a decided set made at the splits past its
    own, in the order the live drive meets them, as ``(boundary key, way)`` —
    last first, for popping.

    The survivors ARE the live parse's continuation with the set's way taken,
    so a split they all came through, the same way, is the next boundary the
    live drive asks, and its answer is already known: the other ways died, or
    met these and were ranked below them, exactly as a set asked there would
    settle them. The plan stops at the first split some survivor has not
    reached, or where two part.
    """
    plan: list[tuple[tuple[Any, ...], int]] = []
    at = 1
    while survivors and all(len(reading.path) > at for reading in survivors):
        choices = {(reading.levels[at].key, reading.path[at]) for reading in survivors}
        if len(choices) != 1:
            break
        plan.append(choices.pop())
        at += 1
    plan.reverse()
    return plan


def _near(side: Side) -> tuple[Any, ...]:
    """What two sides that meet must share, cheaply read: their position, the
    sub-runs left to settle, and their stack's depth and top frame."""
    stack = side[0]
    if not stack:
        return (side[1], -1)
    top = stack[-1]
    return (side[1], len(side[4]), len(stack), id(top.arm), top.i)


def meeting(side: Side) -> tuple[Any, ...]:
    """What two sides must share to have one future: a completed side its
    position alone; any other its position, the sub-runs it still has to
    settle, and its control state."""
    if not side[0]:
        return (side[1], "done")
    return (side[1], len(side[4]), control_signature(side[0], side[1]))


def _built(side: Side, shape: tuple[Any, ...]) -> Any:
    """What a side built since ``shape`` was taken: a completed side's root
    output, any other's pending values."""
    return side[3] if not side[0] else pending_values(side[0], shape)


def _parted(one: Strand, other: Strand) -> int:
    """The split where two readings parted: the first their paths differ at."""
    for at, (mine, theirs) in enumerate(zip(one.path, other.path)):
        if mine != theirs:
            return at
    return min(len(one.path), len(other.path)) - 1


def ranked_level(one: Strand, other: Strand, first: int) -> int:
    """The split two readings that parted at ``first`` are ranked at, or ``-1``.

    A split whose choice both readings rolled back — its frames dropped from
    the same depth on, by the same caller settling the same sub-run on
    something else (:func:`_rolled_back`) — left them in one state, so its
    choice decided nothing and the next split they part at is ranked instead.
    That split must be the same one on both: taken in one control state at one
    position, as every split between the two must be.
    """
    for at in range(first, min(len(one.path), len(other.path))):
        mine, theirs = one.levels[at], other.levels[at]
        if at > first and control_signature(mine.stack, mine.pos) != control_signature(
            theirs.stack, theirs.pos
        ):
            return -1
        if one.path[at] != other.path[at] and not _rolled_back(one, other, at):
            return at
    return -1


def _rolled_back(one: Strand, other: Strand, at: int) -> bool:
    """Whether both readings dropped split ``at``'s frames from one depth on:
    equal completions below it, and that depth's unreadable on both."""
    for left, right in zip(_at(one, at)[5] or (), _at(other, at)[5] or ()):
        if left != right or left == UNSEEN:
            return left == right == UNSEEN
    return False


def _at(reading: Strand, at: int) -> Side:
    """``reading`` as a side of split ``at``: its ledger and copies relative to
    the stack that split was taken on — the completions frozen since, and the
    reading's own for the frames still open — and its own step there."""
    level = reading.levels[at]
    ledger, copies = reading.side[5] or [], reading.side[6]
    ends: list[int] = []
    frames: list[Frame[Any]] = []
    for depth in range(len(level.stack)):
        done = level.done.get(depth)
        end, frame = (ledger[depth], copies[depth]) if done is None else done
        ends.append(end)
        frames.append(frame)
    side = reading.side
    return (
        side[0],
        side[1],
        side[2],
        side[3],
        side[4],
        ends,
        frames,
        reading.forks[at],
    )


def split_children(reading: Strand, split: Split) -> list[Strand]:
    """The readings a split replaces ``reading`` with: each level it came
    through freezing what completed before the split, and a level of its own.
    A reading keeping no ledger freezes nothing: nothing will rank it."""
    ledger, copies = reading.side[5], reading.side[6]
    levels = reading.levels
    if ledger is not None:
        levels = tuple(
            level._replace(
                done={
                    **level.done,
                    **{
                        depth: (ledger[depth], copies[depth])
                        for depth in range(len(level.stack))
                        if depth not in level.done and ledger[depth] != PENDING
                    },
                }
            )
            for level in levels
        )
    levels += (Level(split.stack, split.pos, {}, split.key),)
    return [
        Strand(child, reading.path + (index,), reading.forks + (child[7],), levels)
        for index, child in enumerate(split.children)
    ]
