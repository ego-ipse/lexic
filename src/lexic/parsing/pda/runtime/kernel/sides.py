"""Boundary sides — the stacks a verdict is asked on, and the sub-runs they settle.

Shed from :mod:`~lexic.parsing.pda.runtime.kernel.verdicts` by the file-size rule
as a host class :class:`~lexic.parsing.pda.runtime.kernel.verdicts.Verdicts`
inherits: a side is a structural copy of the live stack with one decision taken,
driven one copied frame at a time, recording where each completes (its ledger)
and settling each attempt sub-run it stands inside as that sub-run's live caller
would (:meth:`Sides._settle_floor`).
"""

from __future__ import annotations

from typing import Any

from lexic.exceptions import LexicError
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    BUILD_TRANSPARENT,
    GATE_ATTEMPT,
    OP_GRP,
    OP_REF,
    OP_REF1,
)
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import (
    Audit,
    Floor,
    KernelCaches,
    RouteLane,
    Side,
    frames_copy,
    sole_admitted,
)
from lexic.parsing.pda.runtime.build import (
    Frame,
)
from lexic.parsing.pda.runtime.islands import IslandPolicy
from lexic.parsing.pda.runtime.matchers import chase_dispatch
from lexic.parsing.product import Completed
from lexic.parsing.product.tree import CompletionResult

__all__ = [
    "PENDING",
    "Sides",
    "UNSEEN",
    "auditing",
    "descending",
    "entered",
    "iterating",
    "landing",
    "once",
    "pending",
    "recorded",
]

PENDING, UNSEEN = -1, -2
"""A side's ledger entry for a copied frame still on its stack, and for one
whose completion the ledger cannot read — a sub-run settled there."""


class Sides[Carry]:
    """Side construction and floors, hosted for :class:`Verdicts` to inherit.

    Declares the kernel surface it reads and the driver and attempt methods a
    side re-enters.
    """

    __slots__ = ()

    tables: PdaTables
    text: str
    pos: int
    stack: list[Frame[Carry]]
    policy: IslandPolicy[Carry]
    _caches: KernelCaches[Carry]
    _routes: RouteLane | None

    def _drive(self, floor: int = 0, limit: int = -1) -> None:
        """Provided by the kernel — drain the frame stack down to ``floor``."""
        raise NotImplementedError

    def _sink_for(self, frame: Frame[Carry], arm: FlatArm, i: int) -> list[Carry]:
        """Provided by the kernel — item ``i``'s lazily-allocated sink."""
        raise NotImplementedError

    def attempt(
        self,
        clone: FlatClone[Carry],
        out: list[Carry],
        ran: int = -1,
        got: tuple[int, list[Carry]] | None = None,
    ) -> None:
        """Provided by ``Attempting`` — run an attempt clone's entries."""
        raise NotImplementedError

    def _attempt_settle(
        self,
        frame: Frame[Carry],
        arm: FlatArm,
        i: int,
        pos: int,
        got: tuple[int, list[Carry]] | None,
    ) -> int:
        """Provided by ``Attempting`` — commit an iteration or close the loop."""
        raise NotImplementedError

    def _attempt_audit(
        self,
        clone: FlatClone[Carry],
        first: int,
        won: tuple[int, list[Carry]],
        out: list[Carry],
        got: tuple[int, list[Carry]] | None = None,
    ) -> None:
        """Provided by ``Attempting`` — audit an attempt's winner."""
        raise NotImplementedError

    def _forked(self, record: bool = False) -> Side:
        """The live stack forked at the cursor as an undriven :data:`Side`.

        The lane forks with the stack, so whichever side loses takes the routes
        it published with it; the sub-runs the stack sits inside come with it
        too (:meth:`_side_floors`), looked for only when a frame's clone can
        root one. A side that ``record``s keeps a ledger, every copied frame
        pending until it completes, and every copy keeps where its items end
        (:func:`frames_copy`): what the rank reads, and what stopping at each
        copied frame costs, so only a verdict that ranks pays for it.

        :raises ProbeFork: When the stack does not say how to settle one of
            those sub-runs.
        """
        # A retry's drive spends a nesting budget, so it cannot be driven again
        record = record or bool(self._caches.nesting.retry)
        remap: dict[int, list[Any]] = {}
        forked = frames_copy(self.stack, record, remap)
        root: list[Carry] = forked[0].out
        floors: list[Floor] = []
        outer = self._caches.side if self._caches.probing else None
        if outer is not None:
            root, floors = self._inherited_floors(outer, forked, remap)
        for frame in self.stack:
            if frame.clone.sub_root:
                found_root, found = self._side_floors(forked)
                # An entry the side's own drive started at the bottom replaced
                # the one it inherited: its winner is the side's root.
                if outer is None or (found and found[0][0] == 0):
                    root = found_root
                floors += found
                break
        routes = None if self._routes is None else self._routes.forked(forked)
        return (
            forked,
            self.pos,
            routes,
            root,
            floors,
            [PENDING] * len(forked) if record else None,
            [*forked] if record else (),
            (),
        )

    def _side(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[Carry]] | None,
        record: bool = False,
    ) -> Side:
        """One side of a loop boundary, undriven, as a resumable :data:`Side`:
        the live stack forked (:meth:`_forked`) with the boundary decided —
        closed (``taken is None``) or advanced past one taken iteration.

        :raises ProbeFork: When the stack does not say how to settle a sub-run
            it sits inside.
        """
        forked, _at, routes, root, floors, ledger, copies, fork = self._forked(record)
        top = forked[-1]
        if taken is None:
            top.close_loop(i, pos)
            return forked, pos, routes, root, floors, ledger, copies, fork
        top.count += 1
        top.i = i
        self._spliced(forked, arm, i, taken[1])
        return forked, taken[0], routes, root, floors, ledger, copies, fork

    def _spliced(
        self, forked: list[Frame[Carry]], arm: FlatArm, i: int, values: list[Carry]
    ) -> None:
        """``values`` reported into item ``i`` of ``forked``'s top frame, as the
        live drive would into its own."""
        saved = self.stack
        self.stack = forked
        try:
            self._sink_for(forked[-1], arm, i).extend(values)
        finally:
            self.stack = saved

    def _extent_side(
        self, k: int, end: int, value: CompletionResult[Carry], record: bool = False
    ) -> Side:
        """One completion of an island at item ``k`` of the top frame, as a
        side: the live stack forked, the value in the item, the cursor past it.
        An exactly-once item's end is written where the drive would not."""
        forked, pos, routes, root, floors, ledger, copies, _fork = self._forked(record)
        top = forked[-1]
        if isinstance(value, Completed):
            self._spliced(forked, top.arm, k, [value.value])
        if once(top, k) and top.ends:
            top.ends[k + 1] = pos + end
        return forked, pos + end, routes, root, floors, ledger, copies, (k, pos + end)

    def _iteration_side(
        self,
        boundary: tuple[FlatArm, int, int],
        end: int,
        value: CompletionResult[Carry],
        record: bool = False,
    ) -> Side:
        """One completion of an island that is an attempted iteration's whole
        sub-run, as a side: the iteration of item ``i`` at ``pos`` —
        ``boundary`` is ``(arm, i, pos)`` — taken with that completion's
        value, its extent the fork's own step."""
        arm, i, pos = boundary
        values = [value.value] if isinstance(value, Completed) else []
        side = self._side(arm, i, pos, (pos + end, values), record)
        return side[:7] + ((i, pos + end),)

    def _descent_item(self, out: list[Carry]) -> int:
        """The item of the top frame whose sink ``out`` is — the reference a
        frame-less descent reports through — or ``-1`` when no item's is."""
        if not self.stack:
            return -1
        frame = self.stack[-1]
        found = [
            k
            for k in descending(frame)
            if (frame.sinks is not None and frame.sinks[k] is out)
            or (frame.clone.mode == BUILD_TRANSPARENT and frame.out is out)
        ]
        return found[0] if len(found) == 1 else -1

    def _advance(
        self, side: Side, limit: int, shared: bool = False
    ) -> tuple[Side | None, bool]:
        """Drive one side to ``limit`` (``-1`` = to the end); ``None`` if it dies.

        Swapped in and out under one discipline, and counted as probing so
        nested boundaries resolve greedily rather than recursing. Whether that
        greedy resolution SAMPLED a both-viable boundary comes back beside the
        side (``uncertain``): the verdicts read it, since a death or a
        convergence reached through a guess proves nothing. A side drives one
        original frame at a time (:meth:`_drive_floors`).

        :param shared: The drive is the remainder two converged sides share,
            where a refusal is undecidable rather than a death.
        :returns: ``(side | None, uncertain)``.
        """
        caches = self._caches
        saved_stack, saved_pos, saved_routes = self.stack, self.pos, self._routes
        self.stack, self.pos, self._routes = side[0], side[1], side[2]
        caches.probing += 1
        saved_unc, saved_side = caches.uncertain, caches.side
        caches.uncertain = False
        caches.side = side
        try:
            floors = side[4]
            ledger = side[5]
            if floors or ledger is not None:
                self._drive_floors(floors, ledger, limit)
            else:  # the common side: nothing to settle, nothing to record
                self._drive(0, limit)
            if not self.stack and self.pos != len(self.text):
                # Drained short of the end: trailing input. This is the one
                # place a side's completion is decided.
                raise PdaFail(f"trailing input at {self.pos}", self.pos)
            return (
                self.stack,
                self.pos,
                self._routes,
                side[3],
                floors,
                side[5],
                side[6],
                side[7],
            ), caches.uncertain
        except ProbeFork:
            raise  # undecidable is not death: it is the gated engine's
        except LexicError as refusal:
            if shared:  # the common remainder, run once for both sides
                raise ProbeFork(
                    f"lockstep: refusal on the shared remainder: {refusal}", self.pos
                ) from None
            return None, caches.uncertain
        except PdaFail:
            return None, caches.uncertain
        finally:
            caches.probing -= 1
            caches.uncertain, caches.side = saved_unc, saved_side
            self.stack, self.pos = saved_stack, saved_pos
            self._routes = saved_routes

    def _probe(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[Carry]] | None,
    ) -> tuple[Side | None, bool]:
        """One side of a boundary, run to end of input — :meth:`_side` driven
        by :meth:`_advance`; the live stack is never touched.

        :param taken: ``None`` for the stop side; the iteration's
            ``(end, values)`` for the take side.
        :returns: ``(side | None, uncertain)`` — the side, if it completed, and
            whether its drive greedily sampled any both-viable boundary on the
            way (the caller's conservatism).
        :raises ProbeFork: An undecidable boundary — the caller bails
            (undecidable never reads as "this side failed").
        """
        return self._advance(self._side(arm, i, pos, taken), -1)

    def _drive_floors(
        self, floors: list[Floor], ledger: list[int] | None, limit: int
    ) -> None:
        """Drive the swapped-in side, settling each sub-run it drains back to,
        and, where it keeps a ledger, recording where each copied frame
        completes.

        The live parse leaves an attempt sub-run to the Python call that
        started it; a side has no such call, so it drives to the sub-run's floor
        and settles there as that call would (:meth:`_settle_floor`). A side
        with a ledger stops at each copied depth in turn instead — the deepest
        still pending first — and the ledger at a floor holds where what the
        call settled on ends, where that is readable. A failure above a floor
        fails that sub-run, never the side, and a settle that fails in turn
        fails the next floor out. With no stop left it drives on and returns;
        :meth:`_advance` decides completion.

        :raises PdaFail: The side dies.
        """
        failed = False
        depth = _next_stop(floors, ledger, pending(ledger) if ledger else 0)
        while True:
            try:
                if failed:
                    failed = False
                    depth = self._settle_failed(floors, ledger)
                self._drive(max(depth, 0), limit)
                if depth < 0 or len(self.stack) > depth:
                    return  # past the last stop, or paused at the limit
                depth = self._reached(depth, floors, ledger)
            except ProbeFork:
                raise
            except PdaFail, LexicError:
                if not floors:
                    raise
                failed = True

    def _reached(
        self, depth: int, floors: list[Floor], ledger: list[int] | None
    ) -> int:
        """The side drained to ``depth``: recorded, the sub-run there settled,
        and the next stop returned."""
        if ledger is not None:
            ledger[depth] = self.pos
        if floors and floors[-1][0] == depth:
            settled = self._settle_floor(floors.pop(), True)
            if ledger is not None:
                ledger[depth] = self.pos if settled else UNSEEN
        return _next_stop(floors, ledger, depth)

    def _settle_failed(self, floors: list[Floor], ledger: list[int] | None) -> int:
        """The innermost sub-run failed above its floor: settled as its caller
        settles a failure, its frames' completions unreadable, and the next
        stop returned."""
        floor = floors.pop()
        depth = floor[0]
        if ledger is not None:
            ledger[depth:] = [UNSEEN] * (len(ledger) - depth)
        if self._settle_floor(floor, False) and ledger is not None:
            ledger[depth] = self.pos
        return _next_stop(floors, ledger, depth)

    def _settle_floor(self, floor: Floor, derived: bool) -> bool:
        """Settle one sub-run as its live caller would: the attempted
        iteration's commit or close, the attempt's next entry, or the audit's.

        :param derived: Whether the sub-run reached its floor; its values are
            the live prefix its root reported before the fork, then the side's.
        :returns: Whether what now stands at the floor's depth ends where the
            cursor is, for the ledger: a committed iteration, the entry's own
            run winning, or the winner an audit commits — not a closed loop,
            nor an entry another one replaced.
        """
        depth, start, holder, live, loop, entry = floor
        end = self.pos
        got = (end, [*live, *holder]) if derived else None
        del self.stack[depth:]
        self.pos = start
        if loop is not None:
            self._attempt_settle(loop, loop.arm, loop.i, start, got)
            return self.pos != start
        if entry is not None and entry[3] is not None:
            self._attempt_audit(entry[0], entry[2] + 1, entry[3], entry[1], got)
            return True
        if entry is not None:
            self.attempt(entry[0], entry[1], entry[2], got)
            return derived and self.pos == end
        return False

    def _side_floors(
        self, forked: list[Frame[Carry]]
    ) -> tuple[list[Carry], list[Floor]]:
        """The attempt sub-runs the live stack is inside, as ``forked`` settles
        them, and the root output it completes into.

        A sub-run's root frame carries its start (:meth:`_attempt_run`), read
        only on a clone that can root one (``sub_root``); the rest is read off
        the frame below it (:meth:`_floors_at`). A sub-run at the bottom of the
        stack is an entry of the start clone, whose winner splices into the
        run's own holder, so the side's root output is a list of its own.

        :raises ProbeFork: On a sub-run no side settles (:meth:`_audit_at`), or
            one the stack does not attribute to exactly one caller.
        """
        root = forked[0].out
        floors: list[Floor] = []
        for depth, frame in enumerate(self.stack):
            if not frame.clone.sub_root:
                continue
            start = getattr(frame, "start", None)
            if start is None:
                continue
            audit = self._audit_at(depth, start)
            pos = start if audit is None else audit[3]
            holder, live = forked[depth].out, frame.out
            if depth > 0:
                found = self._floors_at(depth, pos, holder, live, forked[depth - 1])
            else:
                owner = entered(self.tables.program.start, frame.clone, self.text, pos)
                if owner is None:
                    raise ProbeFork(f"probe side: an unowned sub-run at {pos}", pos)
                root = []
                found: list[Floor] = [
                    (0, pos, holder, live, None, (owner[0], root, owner[1], None))
                ]
            floors += found if audit is None else auditing(found, audit)
        return root, floors

    def _inherited_floors(
        self,
        outer: Side,
        forked: list[Frame[Carry]],
        remap: dict[int, list[Any]],
    ) -> tuple[list[Carry], list[Floor]]:
        """The sub-runs side ``outer`` still has to settle, and its root
        output, as ``forked`` — a copy of ``outer``'s stack — carries them.

        A list on the stack has an empty copy in ``remap``, so a holder's
        values so far join its live prefix; a list off the stack (a root, or
        an entry's winner list) is copied whole, once, so floors that share it
        still share it.
        """

        def carried(lst: list[Carry]) -> tuple[list[Carry], list[Carry]]:
            """``lst``'s copy, and the values it holds that the copy lacks."""
            got = remap.get(id(lst))
            if got is not None:
                return got, lst
            got = remap[id(lst)] = list(lst)
            return got, []

        floors: list[Floor] = []
        for depth, start, holder, live, loop, entry in outer[4]:
            copy, before = carried(holder)
            if entry is not None:
                entry = (entry[0], carried(entry[1])[0], entry[2], entry[3])
            mine = None if loop is None else forked[depth - 1]
            floors.append((depth, start, copy, [*live, *before], mine, entry))
        return carried(outer[3])[0], floors

    def _audit_at(self, depth: int, start: int) -> Audit | None:
        """The live audit whose sub-run roots at ``depth``, or ``None`` when the
        sub-run there is no audit's (``start`` is a position).

        :raises ProbeFork: On :meth:`_spans_exactly`'s sub-run, which no side
            settles, or an audit with no record.
        """
        if start >= 0:
            return None
        if start != -1:
            raise ProbeFork(f"probe side: inside a span check at {self.pos}", self.pos)
        for audit in self._caches.audits:
            if audit[0] == depth:
                return audit
        raise ProbeFork(f"probe side: an audit with no record at {self.pos}", self.pos)

    def _floors_at(
        self,
        depth: int,
        start: int,
        holder: list[Carry],
        live: list[Carry],
        mine: Frame[Carry],
    ) -> list[Floor]:
        """The sub-run whose root frame stands at ``depth``, read off the frame
        below it — ``mine`` is the side's copy of that frame.

        Every reading the frame admits is collected and exactly one must
        survive: an attempted iteration of its current item, alone or around
        the attempt entry its payload runs; or an attempt entry of the item it
        is descending into (a quantified descent stands AT the item, an
        exactly-once reference just past it).

        :raises ProbeFork: When none or several readings survive.
        """
        below, root, text = self.stack[depth - 1], self.stack[depth].clone, self.text
        readings: list[list[Floor]] = []
        if iterating(below):
            payload = below.arm.payloads[below.i]
            owner = entered(payload, root, text, start)
            if landing(payload, text, start) is root:
                readings.append([(depth, start, holder, live, mine, None)])
            elif owner is not None:
                loop: list[Carry] = []
                readings.append(
                    [
                        (depth, start, loop, [], mine, None),
                        (
                            depth,
                            start,
                            holder,
                            live,
                            None,
                            (owner[0], loop, owner[1], None),
                        ),
                    ]
                )
        for k in descending(below):
            owner = entered(below.arm.payloads[k], root, text, start)
            if owner is not None:
                out = self._sink_for(mine, mine.arm, k)
                readings.append(
                    [
                        (
                            depth,
                            start,
                            holder,
                            live,
                            None,
                            (owner[0], out, owner[1], None),
                        )
                    ]
                )
        if len(readings) != 1:
            raise ProbeFork(f"probe side: an unowned sub-run at {start}", start)
        return readings[0]


def _next_stop(floors: list[Floor], ledger: list[int] | None, depth: int) -> int:
    """Where a side's drive stops next, having just stopped at ``depth``: one
    copied frame further out where it keeps a ledger, else the innermost
    sub-run's floor; ``-1`` for none."""
    if ledger is not None:
        return depth - 1
    return floors[-1][0] if floors else -1


def pending(ledger: list[int]) -> int:
    """How many of a side's copied frames are still on its stack: they
    complete deepest first, so they are the ledger's pending prefix."""
    count = 0
    for end in ledger:
        if end != PENDING:
            break
        count += 1
    return count


def once(frame: Frame, k: int) -> bool:
    """Whether item ``k`` of ``frame``'s arm derives one step: an exactly-once
    reference, or an optional — not a loop, whose step is where it ends."""
    return frame.arm.kinds[k] == OP_REF1 or frame.arm.his[k] == 1


def recorded(frame: Frame, k: int) -> int:
    """Where item ``k`` of ``frame`` ended, as its build recorded it; ``-1``
    where the frame keeps no ends."""
    ends = frame.ends
    return -1 if ends is None else ends[k + 1]


def iterating(frame: Frame) -> bool:
    """Whether ``frame`` may stand in an attempted iteration of its current
    item: an attempt-gated reference past its minimum, short of its maximum."""
    arm, i, count = frame.arm, frame.i, frame.count
    if i >= arm.n or arm.gate_kinds[i] != GATE_ATTEMPT:
        return False
    if arm.kinds[i] not in (OP_REF, OP_GRP) or count < arm.los[i]:
        return False
    return arm.his[i] < 0 or count < arm.his[i]


def descending(frame: Frame) -> list[int]:
    """The items ``frame`` may be descending into: its current one once a
    quantified descent has counted itself (an attempted item's only up to its
    minimum), and the one before when that is an exactly-once reference, which
    advances before it descends."""
    arm, i, count = frame.arm, frame.i, frame.count
    found = [i - 1] if 0 < i <= arm.n and arm.kinds[i - 1] == OP_REF1 else []
    if i >= arm.n or arm.kinds[i] not in (OP_REF, OP_GRP) or count < 1:
        return found
    if arm.gate_kinds[i] == GATE_ATTEMPT and count > arm.los[i]:
        return found
    return [i, *found]


def auditing(found: list[Floor], audit: Audit) -> list[Floor]:
    """``found`` with its innermost floor's entry caller turned into the
    auditing one: the same attempt clone and list, the entry the audit runs,
    carrying the winner it audits.

    :raises ProbeFork: When the stack's entry is not the one the audit runs.
    """
    *outer, (depth, start, holder, live, loop, entry) = found
    _depth, clone, idx, _pos, won = audit
    if entry is None or entry[0] is not clone or entry[2] != idx:
        raise ProbeFork(f"probe side: an unowned audit at {start}", start)
    return [*outer, (depth, start, holder, live, loop, (clone, entry[1], idx, won))]


def landing(clone: Any, text: str, pos: int) -> FlatClone | None:
    """The clone :meth:`PdaKernel._enter` would push for ``clone`` at ``pos`` —
    or the attempt clone it would run instead; ``None`` when nothing lands.

    The same chase and the same sole-entry substitution, replayed: both are
    functions of the clone, the text and the position alone. A restatement of
    :meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel._settle`'s
    fixpoint rather than a call into one both share: the entry path pays for a
    shared fixpoint's call on every attempt entry (measured +8 to +20 ns a
    call on vyx), and the replay is pinned to the live parse instead.
    """
    while isinstance(clone, FlatClone):
        if clone.mode == BUILD_DISPATCH:
            try:
                clone = chase_dispatch(clone, text, pos)
            except PdaFail:
                return None
            continue
        if clone.attempt is None:
            return clone
        sole = sole_admitted(clone.attempt[1], text, pos)
        if sole is None:
            return clone
        clone = sole
    return None


def entered(
    clone: Any, target: FlatClone, text: str, pos: int
) -> tuple[FlatClone, int] | None:
    """The attempt clone ``clone`` lands on at ``pos``, and the index of its one
    entry whose sub-run pushes ``target`` — or ``None`` when there is no such
    clone or not exactly one such entry."""
    outer = landing(clone, text, pos)
    if outer is None or outer.attempt is None:
        return None
    found = [
        idx
        for idx, entry in enumerate(outer.attempt[1])
        if landing(entry[4], text, pos) is target
    ]
    return (outer, found[0]) if len(found) == 1 else None
