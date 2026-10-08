"""The boundary verdict — whether a both-viable attempted boundary takes,
stops or forks, and the sides it is asked on.

Shed from :mod:`~lexic.parsing.pda.runtime.kernel.decisions` by the file-size
rule as a host class its :class:`~lexic.parsing.pda.runtime.kernel.decisions.Attempting`
inherits, for the same reason that one is a host class: every member reads and
writes the cursor's own state. A side is a structural stack copy with the
boundary decided, driven in lockstep with the other until they converge or run
to end of input; the attempt sub-runs it is inside are recovered from the stack
(:meth:`Verdicts._side_floors`) and settled as their live callers would.
"""

from __future__ import annotations

from typing import Any

from lexic.exceptions import LexicError
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    GATE_ATTEMPT,
    OP_GRP,
    OP_REF,
    OP_REF1,
)
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import (
    REST_ADMITS,
    REST_ADMITS_HARD,
    REST_ASCEND,
    REST_DEAD,
    Audit,
    Floor,
    KernelCaches,
    RouteLane,
    Side,
    arm_rest_scan,
    control_signature,
    frames_copy,
    pending_values,
    sole_admitted,
    value_shape,
)
from lexic.parsing.pda.runtime.build import (
    Frame,
)
from lexic.parsing.pda.runtime.matchers import chase_dispatch

__all__ = [
    "Verdicts",
    "auditing",
    "descending",
    "entered",
    "iterating",
    "landing",
]

_LOCKSTEP_ROUNDS = 32
"""How many convergence rounds a boundary gets before the slow path takes it.
A budget, not a correctness knob: running out costs today's two full probes."""

_LOCKSTEP_STEP = 8
"""Characters to advance both sides by when they stand at the same position but
different control states — small, because convergence is usually one element
away and every character driven past it is wasted."""

_TAKE, _STOP_FORCED, _FORKED = 0, 1, 2
"""A both-viable boundary's resolutions (:meth:`Verdicts._fork_verdict`)."""


class Verdicts[Carry]:
    """The boundary-verdict methods, hosted for ``Attempting`` to inherit.

    Declares the kernel surface it reads, the driver methods it re-enters and
    the attempt entries a side settles a sub-run through.
    """

    __slots__ = ()

    tables: PdaTables
    text: str
    pos: int
    stack: list[Frame[Carry]]
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

    def _attempt_choice(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        got: tuple[int, list[Carry]],
    ) -> bool:
        """Whether one successful tentative iteration may commit."""
        # The stored soft continuation over-approximates every viable stop
        # side. Outside it, a successful iteration is forced and the live
        # frame-chain walk cannot add information. Only the overlap population
        # pays the exact continuation classification and fork audit.
        char = self.text[pos : pos + 1]
        chars, negated = arm.gate_data[i][1]  # `admits`, read in place
        cls = (
            REST_DEAD
            if ((char == "" or char in chars) if negated else char not in chars)
            else self._beyond_class(arm, i, pos)
        )
        if self._caches.probing:
            # Inside a probe boundaries resolve GREEDILY by class — probes
            # never nest. The terminator class (a MANDATORY item anywhere up
            # the live chain wants the char) prefers stop; the chain class
            # takes. Either way the probe's outcome becomes a SAMPLED path
            # (uncertain).
            if cls == REST_ADMITS_HARD:
                self._caches.uncertain = True
                return False
            if cls == REST_ADMITS:
                self._caches.uncertain = True
        elif cls in (REST_ADMITS, REST_ADMITS_HARD):
            verdict = self._fork_verdict(arm, i, pos, got)
            if verdict == _STOP_FORCED:
                return False
            if verdict == _FORKED:
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable",
                    pos,
                )
        return True

    def _beyond_class(self, arm: FlatArm, i: int, pos: int) -> int:
        """The boundary's viability CLASS over the whole live chain.

        :returns: :data:`REST_ADMITS_HARD` when a MANDATORY item anywhere up the
            live chain wants the char (the terminator class — stopping is the
            strong prior); :data:`REST_ADMITS` for optional-item viability only
            (the chain class — taking is); :data:`REST_DEAD` when no stop side
            exists. Optional admits never settle the walk — a hard admit
            deeper up outranks them. Each frame up the chain is read from the
            item it is suspended in, which after an ``OP_REF1`` is the one before
            ``frame.i``.
        """
        text = self.text
        verdict, opt = arm_rest_scan(arm, i, text, pos)
        if verdict == REST_ASCEND:
            for frame in self.stack[-2::-1]:
                # OP_REF1 advances past itself before descending; such a frame
                # holds no loop count, a quantified descent always does. An
                # attempt with none committed reads as the reference: a superset.
                at, up = frame.i, frame.arm
                if at and frame.count == 0 and up.kinds[at - 1] == OP_REF1:
                    at -= 1
                verdict, seen = arm_rest_scan(up, at, text, pos)
                opt = opt or seen
                if verdict != REST_ASCEND:
                    break
        if verdict == REST_ADMITS_HARD:
            return REST_ADMITS_HARD
        if verdict == REST_DEAD:
            return REST_ADMITS if opt else REST_DEAD
        return REST_ADMITS if (opt or pos >= len(text)) else REST_DEAD

    def _fork_verdict(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[Carry]],
    ) -> int:
        """A both-viable boundary's resolution — take, stop, or fork.

        Ambiguity is a question about values, asked as the forest gate asks
        it — on completions, one flip at the decision point (a fold is
        compositional; later boundaries get their own audits). Both sides run
        to end-of-input: stop dead → taking is FORCED, soundly (the
        alternative derives nothing); take dead while stop completes → STOP
        is forced (Earley's split answer is maximal SUBJECT TO SUCCESS — the
        gbnf-meta terminator theft resolves here); both complete → equal
        values are a benign split (committed as the take), different values
        are the gated engine's question. A death or a completion either drive
        reached through a greedy guess (``uncertain``) is the guess's as much as
        the boundary's, so it decides nothing and forks.

        :param taken: The iteration's ``(end, values)`` (the take side's seed).
        :returns: :data:`_TAKE` / :data:`_STOP_FORCED` / :data:`_FORKED`.
        """
        settled = self._lockstep_verdict(arm, i, pos, taken)
        if settled is not None:
            return settled
        stop, stop_unc = self._probe(arm, i, pos, None)
        if stop is None:
            return _FORKED if stop_unc else _TAKE
        take, take_unc = self._probe(arm, i, pos, taken)
        if take is None:
            return _FORKED if take_unc else _STOP_FORCED
        if stop_unc or take_unc or not same_value(take, stop):
            return _FORKED
        return _TAKE

    def _lockstep_verdict(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[Carry]],
    ) -> int | None:
        """The boundary settled by CONVERGENCE, or ``None`` to run it the long way.

        Running both sides to end-of-input costs O(remaining) per boundary, and
        boundary count grows with the input — the parse is quadratic, and 92% of
        a pipe-heavy vyx packet's wall clock sits in those probes. But the two
        sides differ ONLY in the boundary decision, so they reconverge quickly:
        once they stand at the same position with the same control state and
        the same sub-runs still to settle, the stack (which IS the
        continuation) guarantees them the same future, and the whole question
        reduces to the values each built on the way there.

        Three outcomes are decidable here, all of them the SAME answers the
        end-of-input comparison gives:

        - **converged, values agree** — the parses build one value; a benign
          split, committed as the take. This is the common case, and it costs
          O(1) instead of O(remaining).
        - **converged, values differ** — the remainder is COMMON, so it is run
          ONCE (not twice) to see whether it completes at all: completing makes
          the difference real (a fork); dying means neither side completes, and
          a dead stop side is :data:`_TAKE` exactly as before. A REFUSAL there
          is the exception: a completion that refuses reads the values it
          gathered, which differ between the sides, so running the left side's
          remainder says nothing about the right's, and the boundary is
          undecidable (:meth:`_advance` raises :class:`ProbeFork`).
        - **the STOP side dies** — :data:`_TAKE`, since the caller tests
          ``stop is None`` first regardless; a dead TAKE side does not settle
          it, turning on the stop side reaching end-of-input, unestablished.

        A death the stop side's own drive reached through a greedy guess, and a
        mid-parse convergence either side's did, decide nothing and fork, as at
        end of input (:meth:`_fork_verdict`).

        No convergence in the budget returns ``None``: the caller runs today's
        comparison. A :class:`ProbeFork` PROPAGATES — undecidable is not death.

        :returns: The verdict, or ``None`` when the long way must decide.
        """
        shape = value_shape(self.stack)
        left: Side | None = self._side(arm, i, pos, None)
        right: Side | None = self._side(arm, i, pos, taken)
        left_unc = right_unc = False
        for _round in range(_LOCKSTEP_ROUNDS):
            if left is None:
                return _FORKED if left_unc else _TAKE
            if right is None:
                return None
            target = max(left[1], right[1])
            if left[1] == right[1]:
                if len(left[4]) == len(right[4]) and control_signature(
                    left[0], left[1]
                ) == control_signature(right[0], right[1]):
                    return self._converged(left, right, shape, left_unc or right_unc)
                target += _LOCKSTEP_STEP
            left, sampled = self._advance(left, target)
            left_unc = left_unc or sampled
            right, sampled = self._advance(right, target)
            right_unc = right_unc or sampled
        return None

    def _converged(
        self,
        left: Side,
        right: Side,
        shape: tuple[Any, ...],
        guessed: bool,
    ) -> int | None:
        """The verdict once both sides share a position and a control state.

        Only the values built SINCE the boundary are compared — ``shape`` is
        the watermark taken there, and both sides inherited everything below it
        from one stack. Sides that converged by COMPLETING hold empty stacks,
        so they agree here, base-preserving: two completed carvings are the
        ranked verdict's to compare and F2-check, not convergence's.

        :param guessed: Whether either side's drive guessed on the way here.
        """
        if same_value(pending_values(left[0], shape), pending_values(right[0], shape)):
            return _FORKED if guessed and left[0] else _TAKE
        done, sampled = self._advance(left, -1, shared=True)
        if done is None:  # the common remainder completes on neither side
            return _FORKED if guessed or sampled else _TAKE
        return _FORKED

    def _side(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[Carry]] | None,
    ) -> Side:
        """One side of the boundary, undriven, as a resumable :data:`Side`.

        A structural stack copy with the boundary decided — closed
        (``taken is None``) or advanced past one taken iteration — handed back
        undriven so the caller can run it to the end or advance it in step with
        the other. The lane forks with the stack, so whichever side loses takes
        the routes it published with it; the sub-runs the boundary sits inside
        come with it too (:meth:`_side_floors`), looked for only when a frame's
        clone can root one.

        :raises ProbeFork: When the stack does not say how to settle one of
            those sub-runs.
        """
        forked = frames_copy(self.stack)
        root: list[Carry] = forked[0].out
        floors: list[Floor] = []
        for frame in self.stack:
            if frame.clone.sub_root:
                root, floors = self._side_floors(forked)
                break
        routes = None if self._routes is None else self._routes.forked(forked)
        top = forked[-1]
        if taken is None:
            top.close_loop(i, pos)
            return forked, pos, routes, root, floors
        top.count += 1
        top.i = i
        saved = self.stack
        self.stack = forked
        try:
            self._sink_for(top, arm, i).extend(taken[1])
        finally:
            self.stack = saved
        return forked, taken[0], routes, root, floors

    def _advance(
        self, side: Side, limit: int, shared: bool = False
    ) -> tuple[Side | None, bool]:
        """Drive one side to ``limit`` (``-1`` = to the end); ``None`` if it dies.

        Swapped in and out under one discipline, and counted as probing so
        nested boundaries resolve greedily rather than recursing. Whether that
        greedy resolution SAMPLED a both-viable boundary comes back beside the
        side (``uncertain``): the verdicts read it, since a death or a
        convergence reached through a guess proves nothing. A side carrying
        sub-runs drives floor by floor (:meth:`_drive_floors`).

        :param shared: The drive is the remainder two converged sides share,
            where a refusal is undecidable rather than a death.
        :returns: ``(side | None, uncertain)``.
        """
        caches = self._caches
        saved_stack, saved_pos, saved_routes = self.stack, self.pos, self._routes
        self.stack, self.pos, self._routes = side[0], side[1], side[2]
        caches.probing += 1
        saved_unc = caches.uncertain
        caches.uncertain = False
        try:
            floors = side[4]
            if floors:
                self._drive_floors(floors, limit)
            else:
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
            caches.uncertain = saved_unc
            self.stack, self.pos = saved_stack, saved_pos
            self._routes = saved_routes

    def _probe(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[Carry]] | None,
    ) -> tuple[list[Carry] | None, bool]:
        """One side of a boundary, run to end of input — :meth:`_side` driven
        by :meth:`_advance`; the live stack is never touched.

        :param taken: ``None`` for the stop side; the iteration's
            ``(end, values)`` for the take side.
        :returns: ``(values | None, uncertain)`` — the root output of a side
            that completed, and whether its drive greedily sampled any
            both-viable boundary on the way (the caller's conservatism).
        :raises ProbeFork: An undecidable boundary — the caller bails
            (undecidable never reads as "this side failed").
        """
        done, sampled = self._advance(self._side(arm, i, pos, taken), -1)
        return (None if done is None else done[3]), sampled

    def _drive_floors(self, floors: list[Floor], limit: int) -> None:
        """Drive the swapped-in side, settling each sub-run it drains back to.

        The live parse leaves an attempt sub-run to the Python call that
        started it; a side has no such call, so it drives to one floor at a
        time and settles there as that call would (:meth:`_settle_floor`). A
        failure above a floor fails that sub-run, never the side, and a settle
        that fails in turn fails the next floor out. With no floor left it
        drives on and returns; :meth:`_advance` decides completion.

        :raises PdaFail: The side dies.
        """
        failed = False
        while True:
            try:
                if failed:
                    failed = False
                    self._settle_floor(floors.pop(), False)
                depth = floors[-1][0] if floors else 0
                self._drive(depth, limit)
                if len(self.stack) > depth or not floors:
                    return  # paused at the limit, or past the last floor
                self._settle_floor(floors.pop(), True)
            except ProbeFork:
                raise
            except PdaFail, LexicError:
                if not floors:
                    raise
                failed = True

    def _settle_floor(self, floor: Floor, derived: bool) -> None:
        """Settle one sub-run as its live caller would: the attempted
        iteration's commit or close, the attempt's next entry, or the audit's.

        :param derived: Whether the sub-run reached its floor; its values are
            the live prefix its root reported before the fork, then the side's.
        """
        depth, start, holder, live, loop, entry = floor
        got = (self.pos, [*live, *holder]) if derived else None
        del self.stack[depth:]
        self.pos = start
        if loop is not None:
            self._attempt_settle(loop, loop.arm, loop.i, start, got)
        elif entry is not None and entry[3] is not None:
            self._attempt_audit(entry[0], entry[2] + 1, entry[3], entry[1], got)
        elif entry is not None:
            self.attempt(entry[0], entry[1], entry[2], got)

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
