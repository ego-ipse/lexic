"""The attempt/probe method group — ``PdaKernel``'s decision half.

Shed from the kernel by the file-size rule as a host class the kernel
inherits: the group reads and writes the cursor's own state (``pos``,
``stack``, ``_caches``), so its members stay methods — the two entries the
driver calls (:meth:`Attempting.attempt`,
:meth:`Attempting.attempt_iteration`) are the group's public surface. The class
carries no slots of its own — every attribute it reads is declared by the kernel.

The vocabulary: a both-viable boundary's viability CLASS
(:func:`_arm_rest_scan` walked over the live chain), the probe (one side
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
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
)
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import (
    KernelCaches,
    RouteLane,
    Side,
    admits,
    control_signature,
    frames_copy,
    pending_values,
    sole_admitted,
    value_shape,
    values_agree,
)
from lexic.parsing.pda.runtime.build import F_ARM, F_COUNT, F_ENDS, F_I, F_OUT

__all__ = ["Attempting", "sole_admitted"]

_LOCKSTEP_ROUNDS = 32
"""How many convergence rounds a boundary gets before the slow path takes it.
A budget, not a correctness knob: running out costs today's two full probes."""

_LOCKSTEP_STEP = 8
"""Characters to advance both sides by when they stand at the same position but
different control states — small, because convergence is usually one element
away and every character driven past it is wasted."""

_DEAD, _ASCEND, _ADMITS, _ADMITS_HARD = 0, 1, 2, 3
"""An arm-rest walk's verdicts: a mandatory non-admitting item kills the
stop side; a fully-skippable rest defers to the enclosing frame; an
admitting OPTIONAL item is same-arm chain viability (the greedy split);
an admitting MANDATORY item is the terminator-theft shape — a possessive
take would steal the char the arm's own continuation requires, so the
probes decide (gbnf-meta's rule terminator: ``ws | '\n' next-rule``)."""

_TAKE, _STOP_FORCED, _FORKED = 0, 1, 2
"""A both-viable boundary's resolutions (:meth:`Attempting._fork_verdict`)."""


def _item_admits(arm: FlatArm, j: int, char: str) -> bool:
    """MAY item ``j`` consume ``char`` first — conservative for clone items."""
    if char == "":
        return False
    k = arm.kinds[j]
    payload = arm.payloads[j]
    if k in (OP_LIT, OP_LIT1):
        return payload[0] == char
    if k in (OP_CC, OP_CC1):
        chars, negated = payload
        return (char not in chars) if negated else char in chars
    if k in (OP_FAIL, OP_ISLAND):
        return True  # no FIRST at hand — MAY (a spurious probe is safe)
    return _clone_admits(payload, char)


def _clone_admits(clone: FlatClone, char: str) -> bool:
    """MAY ``clone`` consume ``char`` first (selector union; default ⇒ MAY)."""
    if clone.attempt is not None:
        return any(admits(char, c, n) for c, n, _re, _win, _sub in clone.attempt[1])
    if clone.kwin_selectors is not None or clone.pn_selectors is not None:
        return True  # windowed selection — MAY
    if clone.default is not None:
        return True  # a nullable default may defer admission further down
    for chars, negated, _arm in clone.selectors:
        if (char not in chars) if negated else char in chars:
            return True
    return False


def _arm_rest_scan(arm: FlatArm, i: int, char: str) -> tuple[int, bool]:
    """The rest-of-arm walk past item ``i`` — ``(verdict, optional-admit seen)``.

    An optional admitting item does NOT settle the walk (both the chain and
    the terminator class can coexist — gbnf's ``bar-arm*`` admits the newline
    the rule's MANDATORY ``nl`` also wants, and the hard class must win); a
    mandatory item settles it either way (admits → the terminator class;
    refuses → the char cannot flow past, the stop side is dead).
    """
    opt = False
    for j in range(i + 1, arm.n):
        if _item_admits(arm, j, char):
            if arm.los[j] > 0:
                return _ADMITS_HARD, opt
            opt = True
        elif arm.los[j] > 0:
            return _DEAD, opt
    return _ASCEND, opt


def _composes(follow: Any, text: str, end: int) -> bool:
    """Whether an arm ending at ``end`` can be extended in ANY context.

    The rule's soft FOLLOW over-approximates what may come next, so a next
    character outside it proves this reading dead wherever the rule is used.
    End of input composes: nothing follows, and a rule that may end the parse
    carries the sentinel rather than a character.
    """
    return end >= len(text) or follow.has(text[end : end + 1])


def _close_loop(frame: list[Any], i: int, pos: int) -> int:
    """Close the loop at the current count — the driver continues past ``i``."""
    frame[F_COUNT] = 0
    frame[F_I] = i + 1
    frame[F_ENDS][i] = pos
    return i + 1


class Attempting:
    """The attempt/probe methods, hosted for the kernel to inherit.

    Declares the kernel surface it reads (the kernel's own slots and the
    driver methods it re-enters); :meth:`attempt` and
    :meth:`attempt_iteration` are the entries the driver calls.
    """

    __slots__ = ()

    text: str
    pos: int
    stack: list[list[Any]]
    _caches: KernelCaches
    _routes: RouteLane | None

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """Provided by the kernel — push (or inline) ``clone``'s frame."""
        raise NotImplementedError

    def _drive(self, floor: int = 0, limit: int = -1) -> None:
        """Provided by the kernel — drain the frame stack down to ``floor``."""
        raise NotImplementedError

    def _sink_for(self, frame: list[Any], arm: FlatArm, i: int) -> list[Any]:
        """Provided by the kernel — item ``i``'s lazily-allocated sink."""
        raise NotImplementedError

    def _island(self, name: str, sink: list[object]) -> None:
        """Provided by the kernel — the windowed Earley island splice."""
        raise NotImplementedError

    def attempt_iteration(
        self, frame: list[Any], arm: FlatArm, i: int, pos: int
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
        char = self.text[pos : pos + 1]
        first = arm.gate_data[i][0]
        if not admits(char, *first):
            return _close_loop(frame, i, pos)
        k = arm.kinds[i]
        if k in (OP_ISLAND, OP_FAIL):  # no (end, values) to fork-probe
            if self._stop_viable(arm, i, char):
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable",
                    pos,
                )
            return self._attempt_island(frame, arm, i, pos)
        got = self._attempt_run(arm.payloads[i], pos)
        if got is None or got[0] == pos:
            return _close_loop(frame, i, pos)
        if not self._attempt_choice(arm, i, pos, got):
            return _close_loop(frame, i, pos)
        end, values = got
        self._sink_for(frame, arm, i).extend(values)
        frame[F_COUNT] += 1
        self.pos = end
        return i

    def _attempt_choice(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        got: tuple[int, list[object]],
    ) -> bool:
        """Whether one successful tentative iteration may commit."""
        # The stored soft continuation over-approximates every viable stop
        # side. Outside it, a successful iteration is forced and the live
        # frame-chain walk cannot add information. Only the overlap population
        # pays the exact continuation classification and fork audit.
        char = self.text[pos : pos + 1]
        soft = arm.gate_data[i][1]
        cls = self._beyond_class(arm, i, char) if admits(char, *soft) else _DEAD
        if self._caches.probing:
            # Inside a probe boundaries resolve GREEDILY by class — probes
            # never nest. The terminator class (a MANDATORY item anywhere up
            # the live chain wants the char) prefers stop; the chain class
            # takes. Either way the probe's outcome becomes a SAMPLED path
            # (uncertain).
            if cls == _ADMITS_HARD:
                self._caches.uncertain = True
                return False
            if cls == _ADMITS:
                self._caches.uncertain = True
        elif cls in (_ADMITS, _ADMITS_HARD):
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

        :returns: :data:`_ADMITS_HARD` when a MANDATORY item anywhere up the
            live chain wants the char (the terminator class — stopping is the
            strong prior); :data:`_ADMITS` for optional-item viability only
            (the chain class — taking is); :data:`_DEAD` when no stop side
            exists. Optional admits never settle the walk — a hard admit
            deeper up outranks them.
        """
        verdict, opt = _arm_rest_scan(arm, i, char)
        if verdict == _ASCEND:
            for frame in self.stack[-2::-1]:
                verdict, o = _arm_rest_scan(frame[F_ARM], frame[F_I], char)
                opt = opt or o
                if verdict != _ASCEND:
                    break
        if verdict == _ADMITS_HARD:
            return _ADMITS_HARD
        if verdict == _DEAD:
            return _ADMITS if opt else _DEAD
        return _ADMITS if (opt or char == "") else _DEAD

    def _stop_viable(self, arm: FlatArm, i: int, char: str) -> bool:
        """Whether the boundary char is viable BEYOND another iteration —
        the island branch's trigger (:meth:`_beyond_class` in truth form)."""
        return self._beyond_class(arm, i, char) in (_ADMITS, _ADMITS_HARD)

    def _attempt_island(self, frame: list[Any], arm: FlatArm, i: int, pos: int) -> int:
        """An attempted ISLAND / fail-island iteration — failure closes the loop."""
        if arm.kinds[i] == OP_ISLAND:
            sink = self._sink_for(frame, arm, i)
            try:
                self._island(arm.payloads[i], sink)
            except PdaFail:
                pass
            else:
                frame[F_COUNT] += 1
                return i
        self.pos = pos
        return _close_loop(frame, i, pos)

    def _fork_verdict(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[object]],
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
        are the gated engine's question.

        :param taken: The iteration's ``(end, values)`` (the take side's seed).
        :returns: :data:`_TAKE` / :data:`_STOP_FORCED` / :data:`_FORKED`.
        """
        settled = self._lockstep_verdict(arm, i, pos, taken)
        if settled is not None:
            return settled
        stop, _stop_unc = self._probe(arm, i, pos, None)
        if stop is None:
            return _TAKE
        take, _take_unc = self._probe(arm, i, pos, taken)
        if take is None:
            return _STOP_FORCED
        if len(take) != len(stop) or any(
            not same_value(a, b) for a, b in zip(take, stop)
        ):
            return _FORKED
        return _TAKE

    def _lockstep_verdict(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[object]],
    ) -> int | None:
        """The boundary settled by CONVERGENCE, or ``None`` to run it the long way.

        Running both sides to end-of-input costs O(remaining) per boundary, and
        boundary count grows with the input — the parse is quadratic, and 92% of
        a pipe-heavy vyx packet's wall clock sits in those probes. But the two
        sides differ ONLY in the boundary decision, so they reconverge quickly:
        once they stand at the same position with the same control state, the
        stack (which IS the continuation) guarantees them the same future, and
        the whole question reduces to the values each built on the way there.

        Three outcomes are decidable here, all of them the SAME answers the
        end-of-input comparison gives:

        - **converged, values agree** — the parses build one value; a benign
          split, committed as the take. This is the common case, and it costs
          O(1) instead of O(remaining).
        - **converged, values differ** — the remainder is COMMON, so it is run
          ONCE (not twice) to see whether it completes at all: completing makes
          the difference real (a fork); dying means neither side completes, and
          a dead stop side is :data:`_TAKE` exactly as before.
        - **one side dies during the lockstep** — the verdict is forced, and the
          caller's slow path re-derives it without the bookkeeping.

        Anything else — no convergence inside the budget, an uncertain
        (greedily sampled) side, a :class:`ProbeFork` from deeper in — returns
        ``None``, and the caller runs today's comparison. That escape is what
        makes the change unable to regress correctness: the worst case is the
        behaviour and the answer that shipped before it.

        :returns: The verdict, or ``None`` when the long way must decide.
        """
        shape = value_shape(self.stack)
        left = self._side(arm, i, pos, None)
        right = self._side(arm, i, pos, taken)
        for _round in range(_LOCKSTEP_ROUNDS):
            if left is None or right is None:
                return None  # a dead side — the slow path names which
            target = max(left[1], right[1])
            if left[1] == right[1]:
                if control_signature(left[0], left[1]) == control_signature(
                    right[0], right[1]
                ):
                    return self._converged(left, right, shape)
                target += _LOCKSTEP_STEP
            left = self._advance(left, target)
            right = self._advance(right, target)
        return None

    def _converged(
        self,
        left: Side,
        right: Side,
        shape: tuple[Any, ...],
    ) -> int | None:
        """The verdict once both sides share a position and a control state.

        Only the values built SINCE the boundary are compared — ``shape`` is
        the watermark taken there, and both sides inherited everything below it
        from one stack.
        """
        if values_agree(
            pending_values(left[0], shape), pending_values(right[0], shape)
        ):
            return _TAKE
        done = self._advance(left, -1)
        if done is None or done[1] != len(self.text):
            return _TAKE  # the common remainder does not complete on either side
        return _FORKED

    def _side(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[object]] | None,
    ) -> Side | None:
        """One side of the boundary as its own resumable ``(stack, pos, lane)``.

        The same fork :meth:`_probe` builds — a structural stack copy with the
        boundary decided — but handed back undriven so the caller can advance
        it in step with the other. The lane forks with the stack, so whichever
        side loses takes the routes it published with it.
        """
        forked = frames_copy(self.stack)
        routes = None if self._routes is None else self._routes.forked(forked)
        top = forked[-1]
        if taken is None:
            top[F_COUNT] = 0
            top[F_I] = i + 1
            top[F_ENDS][i] = pos
            return forked, pos, routes
        top[F_COUNT] += 1
        top[F_I] = i
        saved = self.stack
        self.stack = forked
        try:
            self._sink_for(top, arm, i).extend(taken[1])
        finally:
            self.stack = saved
        return forked, taken[0], routes

    def _advance(self, side: Side, limit: int) -> Side | None:
        """Drive one side to ``limit`` (``-1`` = to the end), or ``None`` if it dies.

        Swapped in and out under the same discipline :meth:`_probe` uses, and
        counted as probing so nested boundaries resolve greedily rather than
        recursing — including the greedy resolution of nested boundaries, whose
        ``uncertain`` flag is treated exactly as the end-of-input comparison
        treats it: as information the verdict does not use. (It is read and
        discarded there too — ``_stop_unc``/``_take_unc``.) Disqualifying on it
        was tried and made every pipe-heavy boundary take the slow path, which
        is the whole population this exists for.
        """
        caches = self._caches
        saved_stack, saved_pos, saved_routes = self.stack, self.pos, self._routes
        self.stack, self.pos, self._routes = side[0], side[1], side[2]
        caches.probing += 1
        saved_unc = caches.uncertain
        caches.uncertain = False
        try:
            self._drive(limit=limit)
            return self.stack, self.pos, self._routes
        except PdaFail, LexicError:
            return None
        finally:
            caches.probing -= 1
            caches.uncertain = saved_unc
            self.stack, self.pos = saved_stack, saved_pos
            self._routes = saved_routes

    def attempt(self, clone: FlatClone, out: list[object]) -> None:
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
        :raises PdaFail: When no entry succeeds, or the audit cannot settle.
        """
        follow, entries = clone.attempt
        pos = self.pos
        char = self.text[pos : pos + 1]
        winner = -1
        best: tuple[int, list[object]] | None = None
        for idx, (chars, negated, prefix, window, sub) in enumerate(entries):
            if chars is not None and (  # `admits`, read in place
                (char == "" or char in chars) if negated else (char not in chars)
            ):
                continue
            if prefix is not None and prefix.match(self.text, pos) is None:
                continue
            if window is not None and window.match(self.text, pos) is None:
                continue
            best = self._attempt_run(sub, pos)
            if best is not None:
                if not _composes(follow, self.text, best[0]):
                    # It parses, but its own next character is outside the
                    # rule's FOLLOW, so no context can extend this reading —
                    # a dead arm, not a candidate. Committing would hand the
                    # audit a winner that cannot win, and the audit would then
                    # refuse a longer sibling that CAN (`"#" | "##"` before a
                    # heading's space). FOLLOW over-approximates, so a skip
                    # here drops only arms that are provably dead.
                    best = None
                    continue
                winner = idx
                break
        if best is None:
            raise PdaFail(f"attempt: no arm matches at {pos}", pos)
        self._attempt_audit(entries[winner + 1 :], pos, best[0], follow)
        out.extend(best[1])
        self.pos = best[0]

    def _attempt_audit(
        self, rest: tuple[Any, ...], pos: int, end: int, follow: Any
    ) -> None:
        """Refuse a commit a later admitted entry could contest.

        :param rest: The entries after the winner, in attempt order.
        :param pos: The attempt position.
        :param end: The winner's end.
        :param follow: The rule's soft-FOLLOW CharSet.
        :raises PdaFail: A later entry succeeding on the SAME span (a value
            question this seam does not settle) or on a DIFFERENT span whose
            next character ``follow`` accepts (a cross-span arm choice) —
            either way the gated engine decides.
        """
        char = self.text[pos : pos + 1]
        for chars, negated, prefix, window, sub in rest:
            if chars is not None and (  # `admits`, read in place
                (char == "" or char in chars) if negated else (char not in chars)
            ):
                continue
            if prefix is not None and prefix.match(self.text, pos) is None:
                continue
            if window is not None and window.match(self.text, pos) is None:
                continue
            other = self._attempt_run(sub, pos)
            if other is None:
                continue
            alt = other[0]
            if alt == end or (alt > end and self._spans_exactly(sub, pos, end)):
                raise PdaFail(
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
            if alt >= len(self.text) or follow.has(self.text[alt : alt + 1]):
                raise PdaFail(
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
            bounded = self._attempt_run(sub, pos)
        finally:
            self.text = whole
        return bounded is not None and bounded[0] == end

    def _attempt_run(self, sub: FlatClone, pos: int) -> tuple[int, list[object]] | None:
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

        :param sub: The entry's single-arm clone.
        :param pos: The attempt position.
        :returns: ``(end, values)``, or ``None`` when the arm fails.
        """
        saved_pos = self.pos
        floor = len(self.stack)
        self.pos = pos
        holder: list[object] = []
        try:
            self._enter(sub, holder)
            self._drive(floor)
            return self.pos, holder
        except ProbeFork:
            # Undecidable is NOT failure: swallowing it as this arm's miss
            # would let a later arm commit what the gated engine may refuse.
            raise
        except PdaFail, LexicError:
            return None
        finally:
            del self.stack[floor:]
            self.pos = saved_pos

    def _probe(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[object]] | None,
    ) -> tuple[list[object] | None, bool]:
        """One side of a boundary, run to end-of-input on a copied stack.

        The continuation from a boundary is runnable because the live stack
        IS the continuation: a structural copy (:func:`frames_copy`) with
        the boundary decided — closed (``taken is None``) or advanced past
        one taken iteration — drives to completion under the swapped-stack
        discipline. The completed parse's root values come back for the
        caller's value comparison; the decision applies to the COPY's top
        frame only — the live stack is never touched.

        :param taken: ``None`` for the stop side; the iteration's
            ``(end, values)`` for the take side.
        :returns: ``(values | None, uncertain)`` — the root output on a
            full-input completion, and whether the drive greedily sampled any
            both-viable boundary on the way (the caller's conservatism).
        :raises ProbeFork: An undecidable boundary past the depth cap — the
            caller bails (undecidable never reads as "this side failed").
        """
        caches = self._caches
        saved_stack, saved_pos = self.stack, self.pos
        forked = frames_copy(saved_stack)
        # The lane rides the fork: a probe that publishes a route must not
        # leave it behind on the real stack when the probe is discarded.
        # `None` for every unrouted program, so this costs one test.
        saved_routes = self._routes
        if saved_routes is not None:
            self._routes = saved_routes.forked(forked)
        root_out = forked[0][F_OUT]
        top = forked[-1]
        if taken is None:
            top[F_COUNT] = 0
            top[F_I] = i + 1
            top[F_ENDS][i] = pos
            start = pos
        else:
            top[F_COUNT] += 1
            top[F_I] = i
            start = taken[0]
        self.stack = forked
        self.pos = start
        caches.probing += 1
        saved_unc = caches.uncertain
        caches.uncertain = False
        try:
            if taken is not None:
                self._sink_for(top, arm, i).extend(taken[1])
            self._drive()
            done = root_out if self.pos == len(self.text) else None
            return done, caches.uncertain
        except ProbeFork:
            raise
        except PdaFail, LexicError:
            return None, caches.uncertain
        finally:
            caches.probing -= 1
            caches.uncertain = saved_unc
            self.stack, self.pos = saved_stack, saved_pos
            self._routes = saved_routes
