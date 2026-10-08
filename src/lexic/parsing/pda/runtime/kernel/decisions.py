"""The attempt/probe method group — ``PdaKernel``'s decision half.

Shed from the kernel by the file-size rule as a host class the kernel
inherits: the group reads and writes the cursor's own state (``pos``,
``stack``, ``_caches``), so its members stay methods — the two entries the
driver calls (:meth:`Attempting.attempt`,
:meth:`Attempting.attempt_iteration`) are the group's public surface. The class
carries no slots of its own — every attribute it reads is declared by the kernel.

The vocabulary: a both-viable boundary's viability CLASS
(:func:`arm_rest_scan` walked over the live chain), the probe (one side
run to end-of-input on a structural stack copy), and the three-verdict
fork resolution (take / stop-forced / fork) asked as the forest gate asks
it — on completed VALUES.
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
    OP_FAIL,
    OP_GRP,
    OP_ISLAND,
    OP_REF,
    OP_REF1,
)
from lexic.parsing.pda.compiler.specs import IslandPayload
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
    composes,
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
    "Attempting",
    "auditing",
    "descending",
    "entered",
    "iterating",
    "landing",
    "sole_admitted",
]

_LOCKSTEP_ROUNDS = 32
"""How many convergence rounds a boundary gets before the slow path takes it.
A budget, not a correctness knob: running out costs today's two full probes."""

_LOCKSTEP_STEP = 8
"""Characters to advance both sides by when they stand at the same position but
different control states — small, because convergence is usually one element
away and every character driven past it is wasted."""

_TAKE, _STOP_FORCED, _FORKED = 0, 1, 2
"""A both-viable boundary's resolutions (:meth:`Attempting._fork_verdict`)."""


class Attempting[Carry]:
    """The attempt/probe methods, hosted for the kernel to inherit.

    Declares the kernel surface it reads (the kernel's own slots and the
    driver methods it re-enters); :meth:`attempt` and
    :meth:`attempt_iteration` are the entries the driver calls.
    """

    __slots__ = ()

    tables: PdaTables
    text: str
    pos: int
    stack: list[Frame[Carry]]
    _caches: KernelCaches[Carry]
    _routes: RouteLane | None

    def _enter(self, clone: FlatClone[Carry], out: list[Carry]) -> bool:
        """Provided by the kernel — push (or inline) ``clone``'s frame."""
        raise NotImplementedError

    def _drive(self, floor: int = 0, limit: int = -1) -> None:
        """Provided by the kernel — drain the frame stack down to ``floor``."""
        raise NotImplementedError

    def _sink_for(self, frame: Frame[Carry], arm: FlatArm, i: int) -> list[Carry]:
        """Provided by the kernel — item ``i``'s lazily-allocated sink."""
        raise NotImplementedError

    def _island(self, ref: IslandPayload, sink: list[Carry]) -> None:
        """Provided by the kernel — the windowed Earley island splice.

        ``ref`` is the ``OP_ISLAND`` payload: the island rule's name, what may
        follow it AT THIS OCCURRENCE, and whether that continuation also bounds
        its extent.
        """
        raise NotImplementedError

    def attempt_iteration(
        self, frame: Frame[Carry], arm: FlatArm, i: int, pos: int
    ) -> int:
        """One ATTEMPTED optional loop iteration — failure closes the loop.

        The licensed-loop semantics (:data:`GATE_ATTEMPT`): the gate's FIRST
        admission is a pre-filter, not a commitment. The iteration runs as a
        self-contained sub-run, and a failure — or a zero-width success, which
        could never advance the loop — CLOSES the loop at the current count
        instead of failing the arm. The loop thereby takes maximally subject
        to its iterations actually parsing: the split's defined answer, where
        a committed take would fail the whole arm on any interior mismatch
        (an optional item's FIRST routinely overlaps its successor's).

        A boundary char viable for BOTH the iteration and the loop's soft
        continuation MAY be an arm choice in loop clothing — a shorter extent
        composing into a different-valued whole parse. The one-char signal
        over-approximates wildly (an optional item's FIRST routinely shares a
        separator char with its successor's), so the decision is made by
        TRYING the stop side: the arm-rest probe
        (:func:`~lexic.parsing.pda.compiler.program.lower._rest_clone`) runs from the
        cursor, and only when stopping ALSO parses is the boundary a genuine
        local fork — bailed to the gated engine, whose whole-input view owns
        the question. A failing probe licenses the iteration.

        :returns: The driver continuation index, exactly as
            :meth:`PdaKernel._quant_step`.
        :raises PdaFail: On a genuinely forked boundary (the gated engine
            decides), including every both-viable boundary of an arm-FINAL
            loop (its empty rest-probe succeeds vacuously — stop viability
            then belongs to the enclosing frames, which no local probe sees).
        """
        try:  # the lookahead: indexing, and end of input as the rare exception
            char = self.text[pos]
        except IndexError:
            char = ""
        chars, negated = arm.gate_data[i][0]  # `admits`, read in place
        if (char == "" or char in chars) if negated else char not in chars:
            return frame.close_loop(i, pos)
        k = arm.kinds[i]
        if k in (OP_ISLAND, OP_FAIL):  # no (end, values) to fork-probe
            if self._stop_viable(arm, i, char):
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable",
                    pos,
                )
            return self._attempt_island(frame, arm, i, pos)
        got = self._attempt_run(arm.payloads[i], pos, pos)
        return self._attempt_settle(frame, arm, i, pos, got)

    def _attempt_settle(
        self,
        frame: Frame[Carry],
        arm: FlatArm,
        i: int,
        pos: int,
        got: tuple[int, list[Carry]] | None,
    ) -> int:
        """Commit one attempted iteration's sub-run, or close the loop.

        The tail of :meth:`attempt_iteration`, and what a boundary side runs
        when its drive drains back to a loop iteration it was forked inside.

        :param got: The sub-run's ``(end, values)``, or ``None`` when it failed.
        :returns: The driver continuation index.
        """
        if got is None or got[0] == pos or not self._attempt_choice(arm, i, pos, got):
            return frame.close_loop(i, pos)
        end, values = got
        self._sink_for(frame, arm, i).extend(values)
        frame.count += 1
        self.pos = end
        return i

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
            else self._beyond_class(arm, i, char)
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

    def _beyond_class(self, arm: FlatArm, i: int, char: str) -> int:
        """The boundary's viability CLASS over the whole live chain.

        :returns: :data:`REST_ADMITS_HARD` when a MANDATORY item anywhere up the
            live chain wants the char (the terminator class — stopping is the
            strong prior); :data:`REST_ADMITS` for optional-item viability only
            (the chain class — taking is); :data:`REST_DEAD` when no stop side
            exists. Optional admits never settle the walk — a hard admit
            deeper up outranks them.
        """
        verdict, opt = arm_rest_scan(arm, i, char)
        if verdict == REST_ASCEND:
            for frame in self.stack[-2::-1]:
                verdict, o = arm_rest_scan(frame.arm, frame.i, char)
                opt = opt or o
                if verdict != REST_ASCEND:
                    break
        if verdict == REST_ADMITS_HARD:
            return REST_ADMITS_HARD
        if verdict == REST_DEAD:
            return REST_ADMITS if opt else REST_DEAD
        return REST_ADMITS if (opt or char == "") else REST_DEAD

    def _stop_viable(self, arm: FlatArm, i: int, char: str) -> bool:
        """Whether the boundary char is viable BEYOND another iteration —
        the island branch's trigger (:meth:`_beyond_class` in truth form)."""
        return self._beyond_class(arm, i, char) in (REST_ADMITS, REST_ADMITS_HARD)

    def _attempt_island(
        self, frame: Frame[Carry], arm: FlatArm, i: int, pos: int
    ) -> int:
        """An attempted ISLAND / fail-island iteration — failure closes the loop;
        an island that cannot settle its own extent bails instead."""
        if arm.kinds[i] == OP_ISLAND:
            sink = self._sink_for(frame, arm, i)
            try:
                self._island(arm.payloads[i], sink)
            except ProbeFork:
                raise
            except PdaFail:
                pass
            else:
                frame.count += 1
                return i
        self.pos = pos
        return frame.close_loop(i, pos)

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

    def attempt(
        self,
        clone: FlatClone[Carry],
        out: list[Carry],
        ran: int = -1,
        got: tuple[int, list[Carry]] | None = None,
    ) -> None:
        """Try an attempt clone's entries in order — the third gate class, live.

        Each entry runs as a self-contained sub-run from the cursor
        (:meth:`_attempt_run` — rolled back by construction on failure). The
        first success is audited against the REMAINING admitted entries before
        it commits: a second success on the SAME span is a value question this
        seam does not settle, and one on a DIFFERENT span whose next character
        the rule's continuation accepts is a cross-span arm choice — both bail
        to the gated engine, which refuses iff the ambiguity is real.

        :param clone: The attempt clone (``clone.attempt`` is set).
        :param out: The parent sink the winning arm's values splice into.
        :param ran: The entry whose sub-run already ran, ``got`` its outcome —
            how a boundary side resumes an attempt it was forked inside; the
            live entry passes neither and starts at the first entry. From
            there on the two name the latest entry tried and its outcome, and
            end naming the winner.
        :raises PdaFail: When no entry succeeds, or the audit cannot settle.
        """
        follow, entries = clone.attempt
        pos = self.pos
        char = self.text[pos : pos + 1]
        if got and not composes(follow, self.text, got[0]):
            got = None
        for idx in range(len(entries) if got else ran + 1, len(entries)):
            chars, negated, prefix, window, sub = entries[idx]
            if chars is not None and (  # `admits`, read in place
                (char == "" or char in chars) if negated else (char not in chars)
            ):
                continue
            if prefix is not None and prefix.match(self.text, pos) is None:
                continue
            if window is not None and window.match(self.text, pos) is None:
                continue
            got = self._attempt_run(sub, pos, pos)
            if got is not None:
                if not composes(follow, self.text, got[0]):
                    # It parses, but its own next character is outside the
                    # rule's FOLLOW, so no context can extend this reading —
                    # a dead arm, not a candidate. Committing would hand the
                    # audit a winner that cannot win, and the audit would then
                    # refuse a longer sibling that CAN (`"#" | "##"` before a
                    # heading's space). FOLLOW over-approximates, so a skip
                    # here drops only arms that are provably dead.
                    got = None
                    continue
                ran = idx
                break
        if got is None:
            raise PdaFail(f"attempt: no arm matches at {pos}", pos)
        self._attempt_audit(clone, ran + 1, got, out)

    def _attempt_audit(
        self,
        clone: FlatClone[Carry],
        first: int,
        won: tuple[int, list[Carry]],
        out: list[Carry],
        got: tuple[int, list[Carry]] | None = None,
    ) -> None:
        """Refuse a commit a later admitted entry could contest, then commit it.

        Runs with the cursor at the attempt position. Each audited entry's
        sub-run is wrapped in a record of the audit (:data:`Audit`), the one
        state a fork inside it cannot read off the stack — in a program that
        can fork (``sub_root``); elsewhere nothing reads one.

        :param clone: The attempt clone whose entry ``won``.
        :param first: The first entry still to audit.
        :param won: The winner's ``(end, values)``.
        :param out: The parent sink the winner's values splice into.
        :param got: The outcome of entry ``first - 1``, already run — how a
            boundary side resumes an audit it was forked inside; the live
            audit passes none.
        :raises ProbeFork: As :meth:`_contest` raises.
        """
        pos = self.pos
        entries = clone.attempt[1]
        if got is not None:
            self._contest(entries[first - 1][-1], won[0], got[0], clone)
        char = self.text[pos : pos + 1]
        for idx in range(first, len(entries)):
            chars, negated, prefix, window, sub = entries[idx]
            if chars is not None and (  # `admits`, read in place
                (char == "" or char in chars) if negated else (char not in chars)
            ):
                continue
            if prefix is not None and prefix.match(self.text, pos) is None:
                continue
            if window is not None and window.match(self.text, pos) is None:
                continue
            if not sub.sub_root:  # the program cannot fork: nothing reads it
                got = self._attempt_run(sub, pos, -1)
            else:
                self._caches.audits.append((len(self.stack), clone, idx, pos, won))
                try:
                    got = self._attempt_run(sub, pos, -1)
                finally:
                    self._caches.audits.pop()
            if got is not None:
                self._contest(sub, won[0], got[0], clone)
        out.extend(won[1])
        self.pos = won[0]

    def _contest(
        self, sub: FlatClone[Carry], end: int, alt: int, clone: FlatClone
    ) -> None:
        """Refuse a winner ending at ``end`` that ``sub``'s success at ``alt``
        contests, both from the attempt position at the cursor.

        :raises ProbeFork: A later entry succeeding on the SAME span (a value
            question this seam does not settle) or on a DIFFERENT span whose
            next character the rule's soft FOLLOW accepts (a cross-span arm
            choice) — either way the gated engine decides. Undecidable, not a
            miss: an enclosing attempted iteration re-raises it rather than
            reading it as its own arm failing, which would close the loop and
            commit.
        """
        pos = self.pos
        if alt == end or (alt > end and self._spans_exactly(sub, pos, end)):
            raise ProbeFork(
                f"attempt at {pos}: two arms span [{pos}, {end}) — "
                "a value question for the gated engine",
                pos,
            )
        # End of input composes with whatever can finish there, and the
        # rule's FOLLOW may or may not carry the sentinel — so asking it
        # about `""` answered "cannot compose" for every alternative that
        # consumed to the end, which is exactly when a longer reading is
        # most likely to be the whole parse. Reaching the end is treated
        # as composable: the bail direction, where the gated engine's
        # whole-input view settles it.
        if alt >= len(self.text) or clone.attempt[0].has(self.text[alt : alt + 1]):
            raise ProbeFork(
                f"attempt at {pos}: arm choice spans two ends ({alt}, {end}) "
                "and the alternative could compose",
                pos,
            )

    def _spans_exactly(self, sub: FlatClone, pos: int, end: int) -> bool:
        """Whether ``sub`` also derives exactly ``[pos, end)``.

        An arm has a FAMILY of extents, not one: :meth:`_attempt_run` reports
        only the greedy member, so an arm that overshoots the winner may still
        derive the winner's own span — and two arms over one span is the value
        question this seam refuses. Asked by re-running the arm against the
        text TRUNCATED at ``end``, which is what makes the greedy run stop
        there; a completed parse of a prefix is a genuine derivation of it, so
        the answer cannot be a false positive. Only reachable when the greedy
        extent OVERSHOOTS — an arm that stopped short could not reach ``end``.
        """
        whole = self.text
        self.text = whole[:end]
        try:
            bounded = self._attempt_run(sub, pos, -2)
        finally:
            self.text = whole
        return bounded is not None and bounded[0] == end

    def _attempt_run(
        self, sub: FlatClone[Carry], pos: int, mark: int
    ) -> tuple[int, list[Carry]] | None:
        """One arm attempt as a self-contained sub-run — fail-soft, rolled back.

        Runs ON TOP of the live stack, bounded by a depth watermark (not a
        severed fresh stack): nested boundaries' viability walks and probes
        then see the TRUE continuation — the severed form mis-resolved any
        fork whose alternative lived in an enclosing frame (gbnf-meta's rule
        terminator). EVERY value the arm reports is returned (a transparent
        arm splices several); an EOF completion is a legitimate success; a
        refusing fold (:class:`~lexic.exceptions.LexicError`) fails the ARM,
        not the parse. Deliberately unmemoized — a sub-run's outcome depends
        on the enclosing continuation, so ``(clone, pos)`` is not a sound
        key (and the memo measured zero hits when it was).

        The sub-run's root frame is MARKED with ``mark``
        (:attr:`~lexic.parsing.pda.runtime.build.Frame.start`): the one fact a
        boundary forked inside it cannot read off the stack, so a side can
        settle the sub-run as its caller here would (:meth:`_side_floors`).
        Only where the program can fork (``sub_root``): elsewhere nothing reads
        it, and the store is most of what the mark costs.

        :param sub: The entry's single-arm clone.
        :param pos: The attempt position.
        :param mark: ``pos`` for a loop iteration or an attempt entry, ``-1``
            for an audit's run (its record is on the caches), ``-2`` for
            :meth:`_spans_exactly`'s, which no side settles.
        :returns: ``(end, values)``, or ``None`` when the arm fails.
        """
        saved_pos = self.pos
        floor = len(self.stack)
        self.pos = pos
        holder: list[Carry] = []
        try:
            if self._enter(sub, holder):
                if sub.sub_root:
                    self.stack[floor].start = mark
                self._drive(floor)
            return self.pos, holder
        except ProbeFork:
            # Undecidable is NOT failure: swallowing it as this arm's miss
            # would let a later arm commit what the gated engine may refuse.
            raise
        except PdaFail, LexicError:
            return None
        finally:
            if len(self.stack) > floor:  # a completed drive left none above
                del self.stack[floor:]
            self.pos = saved_pos

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
