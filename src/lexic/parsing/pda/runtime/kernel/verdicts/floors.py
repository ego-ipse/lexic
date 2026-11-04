"""Floors — attempt sub-runs settled where their frames drain back to, as their caller would.

Shed from :mod:`~lexic.parsing.pda.runtime.kernel.verdicts.sides` once the live
drive came to settle sub-runs the same way a side does: a sub-run left on the
stack with no Python call waiting on it — a side forked inside it, or one the
live parse suspended past its in-place depth — is a :data:`Floor`, and one
drive settles both kinds (:meth:`Floors._drive_floors`). A host class
:class:`~.sides.Sides` extends, so its members stay methods on the kernel.
"""

from __future__ import annotations

from typing import Any

from lexic.exceptions import LexicError
from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.specs import IslandPayload
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork, Suspended
from lexic.parsing.pda.runtime.admission import Floor, KernelCaches
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.islands import IslandEnds

__all__ = ["Floors", "PENDING", "UNSEEN", "pending"]

PENDING, UNSEEN = -1, -2
"""A side's ledger entry for a copied frame still on its stack, and for one
whose completion the ledger cannot read — a sub-run settled there."""


class Floors[Carry]:
    """The floor drive, hosted for :class:`~.sides.Sides` to inherit.

    Declares the kernel surface it reads and the attempt methods a settle
    re-enters.
    """

    __slots__ = ()

    pos: int
    stack: list[Frame[Carry]]
    _caches: KernelCaches[Carry]

    def _drive(self, floor: int = 0, limit: int = -1) -> None:
        """Provided by the kernel — drain the frame stack down to ``floor``."""
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
        ran: int,
        won: tuple[int, list[Carry]],
        rivals: list[tuple[int, list[Carry]]] | None,
    ) -> list[tuple[int, list[Carry]]] | None:
        """Provided by ``Attempting`` — audit an attempt's winner."""
        raise NotImplementedError

    def _contest(
        self,
        sub: FlatClone[Carry],
        won: tuple[int, list[Carry]],
        got: tuple[int, list[Carry]],
        clone: FlatClone,
    ) -> bool:
        """Provided by ``Attempting`` — whether ``got`` is a rival of ``won``."""
        raise NotImplementedError

    def _settle_arm(
        self,
        won: tuple[int, list[Carry]],
        rivals: list[tuple[int, list[Carry]]] | None,
        out: list[Carry],
    ) -> None:
        """Provided by ``Attempting`` — commit an audited attempt."""
        raise NotImplementedError

    def _stolen_at(self, floor: int) -> IslandPayload | None:
        """Provided by ``Attempting`` — the island a missed sub-run asks."""
        raise NotImplementedError

    def _stolen_back(
        self, island: IslandPayload | None, pos: int, sub: FlatClone[Carry] | None
    ) -> tuple[int, list[Carry]] | None:
        """Provided by ``Attempting`` — that island's outcome at ``pos``."""
        raise NotImplementedError

    def _iteration_ends(
        self, two: IslandEnds, arm: FlatArm, i: int, pos: int
    ) -> tuple[int, list[Carry]]:
        """Provided by ``Verdicts`` — an iteration that is an island's ends."""
        raise NotImplementedError

    def _drive_floors(
        self,
        floors: list[Floor],
        ledger: list[int] | None,
        limit: int,
        base: int = 0,
        live: bool = False,
    ) -> None:
        """Drive the stack down to ``base``, settling each sub-run it drains
        back to, and, where it keeps a ledger, recording where each copied
        frame completes.

        A sub-run left on the stack has no Python call waiting on it — a side
        is forked inside it, or the live drive suspended it (``live``,
        :meth:`_catch`) — so the drive stops at its floor and settles it there
        as that call would (:meth:`_settle_floor`). A side with a ledger stops
        at each copied depth in turn instead — the deepest still pending
        first — and the ledger at a floor holds where what the call settled on
        ends, where that is readable. A failure above a floor fails that
        sub-run as its call fails one (:meth:`_settle_failed`), never the
        drive, and a settle that fails in turn fails the next floor out. A
        sub-run that suspends inside it is one floor more. With no stop left it
        drives on and returns; :meth:`_advance` decides a side's completion.

        :raises PdaFail: The drive dies.
        """
        failed: Exception | None = None
        depth = _next_stop(floors, ledger, pending(ledger) if ledger else 0)
        while True:
            try:
                if failed is not None:
                    failure, failed = failed, None
                    depth = self._settle_failed(floors, ledger, failure, live)
                self._drive(max(depth, base), limit)
                if depth < 0 or len(self.stack) > depth:
                    return  # past the last stop, or paused at the limit
                depth = self._reached(depth, floors, ledger, live)
            except Suspended as up:  # a sub-run past the depth: one floor more
                floors.extend(reversed(up.floors))
                depth = floors[-1][0]
            except ProbeFork as fork:
                if not floors or not isinstance(fork, IslandEnds):
                    raise
                # Held without its traceback, which holds this frame and so
                # the failure: a cycle only the collector frees.
                failed = fork.with_traceback(None)
            except (PdaFail, LexicError) as failure:
                if not floors:
                    raise
                failed = failure.with_traceback(None)

    def _catch(self, floor: int) -> None:
        """Drive the sub-run rooted at ``floor`` to its outcome, settling each
        sub-run that suspends inside it at its own floor — or, where a drive
        below in the same drive (the same probing level: a side's is its own)
        already does, suspend it for that one.

        The one sub-run at the parse's in-place depth drives this way
        (``Attempting._attempt_run``): every one past it leaves its frames
        pushed and returns, so the Python stack stays this deep. A floor
        abandoned when the drive fails takes its audit record with it, as its
        call would have.

        :raises PdaFail: As the sub-run's own drive would.
        :raises Suspended: Where a drive below settles it.
        """
        scope, level = self._caches.scope, self._caches.probing + 1
        if scope.catching == level:  # one below settles it: it stays pushed
            raise Suspended
        held, scope.catching = scope.catching, level
        floors: list[Floor] = []
        try:
            self._drive_floors(floors, None, -1, floor, True)
        finally:
            scope.catching = held
            while floors:
                self._taken(floors)

    def _reached(
        self, depth: int, floors: list[Floor], ledger: list[int] | None, live: bool
    ) -> int:
        """The drive drained to ``depth``: recorded, the sub-run there settled
        on what its root derived, and the next stop returned."""
        if ledger is not None:
            ledger[depth] = self.pos
        if floors and floors[-1][0] == depth:
            floor = self._taken(floors) if live else floors.pop()
            got = (self.pos, [*floor[3], *floor[2]])
            settled = self._settle_floor(floor, got)
            if ledger is not None:
                ledger[depth] = self.pos if settled else UNSEEN
        return _next_stop(floors, ledger, depth)

    def _settle_failed(
        self,
        floors: list[Floor],
        ledger: list[int] | None,
        failure: Exception,
        live: bool,
    ) -> int:
        """The innermost sub-run failed above its floor: settled as its caller
        settles a failure (:meth:`_missed_at`), its frames' completions
        unreadable, and the next stop returned.

        :raises IslandEnds: An island's ends its caller does not take, for
            the next floor out.
        """
        floor = self._taken(floors) if live else floors.pop()
        depth = floor[0]
        if ledger is not None:
            ledger[depth:] = [UNSEEN] * (len(ledger) - depth)
        got = self._missed_at(floor, failure, live)
        if self._settle_floor(floor, got) and ledger is not None:
            ledger[depth] = self.pos
        return _next_stop(floors, ledger, depth)

    def _missed_at(
        self, floor: Floor, failure: Exception, live: bool
    ) -> tuple[int, list[Carry]] | None:
        """What the caller of ``floor``'s failed sub-run reads, as
        ``Attempting._attempt_run`` and its callers read a failure: the
        rule's island where the root steals, its ends (claimed for the
        sub-run as they are raised, :meth:`_stolen_back`) taken by an
        attempted iteration they are the whole outcome of, and otherwise
        nothing. The stack is unwound to the floor. Ends that reach a floor
        from its drive are raised on, as no sub-run's outcome.

        Only a ``live`` floor's miss steals: it is its sub-run's outcome. A
        side's is one reading's death inside a sub-run the live parse still
        runs; the sub-run misses only when every reading does, and its live
        caller then asks the island. Asked here, the island would answer for
        the rule whatever way the reading took, beside the reading that took
        the other.

        :raises IslandEnds: Ends the caller does not take.
        """
        depth, start, _holder, _live, loop, _entry = floor
        sub = _floor_sub(floor)
        ends = failure if isinstance(failure, IslandEnds) else None
        steals = (
            None
            if not live or ends is not None or isinstance(failure, LexicError)
            else self._stolen_at(depth)
        )
        del self.stack[depth:]
        self.pos = start
        if steals is not None:
            try:
                return self._stolen_back(steals, start, sub)
            except IslandEnds as two:  # claimed for the sub-run: its outcome
                ends = two
        if ends is None:
            return None
        if (
            loop is None
            or ends.root is not loop.arm.payloads[loop.i]
            or ends.pos != start
        ):
            raise ends
        return self._iteration_ends(ends, loop.arm, loop.i, start)

    def _taken(self, floors: list[Floor]) -> Floor:
        """The innermost floor of a live drive, taken off — and, for an
        audited entry's, the audit record its call would have dropped on
        returning."""
        floor = floors.pop()
        entry, audits = floor[5], self._caches.audits
        if entry is not None and entry[3] is not None and audits:
            if audits[-1][:3] == (floor[0], entry[0], entry[2]):
                audits.pop()
        return floor

    def _settle_floor(self, floor: Floor, got: tuple[int, list[Carry]] | None) -> bool:
        """Settle one sub-run as its live caller would on ``got``: the
        attempted iteration's commit or close, the attempt's next entry, or the
        audit's.

        :param got: The sub-run's outcome, ``None`` when it missed.
        :returns: Whether what now stands at the floor's depth ends where the
            cursor is, for the ledger: a committed iteration, the entry's own
            run winning, or the winner an audit commits — not a closed loop,
            nor an entry another one replaced.
        """
        depth, start, _holder, _live, loop, entry = floor
        del self.stack[depth:]
        self.pos = start
        if loop is not None:
            self._attempt_settle(loop, loop.arm, loop.i, start, got)
            return self.pos != start
        if entry is not None and entry[3] is not None:
            self._resume_audit(entry, got)
            return True
        if entry is not None:
            self.attempt(entry[0], entry[1], entry[2], got)
            return got is not None and self.pos == got[0]
        return False

    def _resume_audit(
        self, entry: tuple[Any, ...], got: tuple[int, list[Carry]] | None
    ) -> None:
        """An audit resumed at an audited entry's floor, as the audit would
        have gone on: ``got``, that entry's outcome, contested; the rest
        audited; the kept arm committed."""
        clone, out, idx, won, rivals = entry
        if got is not None and self._contest(
            clone.attempt[1][idx][-1], won, got, clone
        ):
            rivals = [got] if rivals is None else [*rivals, got]
        try:
            self._settle_arm(won, self._attempt_audit(clone, idx, won, rivals), out)
        except Suspended:  # an audited entry's: the kept arm splices into `out`
            Suspended.splicing_into(out)
            raise


def _floor_sub(floor: Floor) -> FlatClone | None:
    """The clone a floor's sub-run runs: its loop item's payload, or its
    attempt entry's sub-clone; ``None`` for a floor no caller settles."""
    loop, entry = floor[4], floor[5]
    if loop is not None:
        return loop.arm.payloads[loop.i]
    return None if entry is None else entry[0].attempt[1][entry[2]][-1]


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
