"""The attempt/probe method group — ``PdaKernel``'s decision half.

Shed from the kernel by the file-size rule as a host class the kernel
inherits: the group reads and writes the cursor's own state (``pos``,
``stack``, ``_caches``), so its members stay methods — the two entries the
driver calls (:meth:`Attempting.attempt`,
:meth:`Attempting.attempt_iteration`) are the group's public surface, and
the reduce twin rides through unchanged. The class carries no slots of its
own — every attribute it reads is declared by the kernel.

The vocabulary: a both-viable boundary's viability CLASS
(:func:`_arm_rest_scan` walked over the live chain), the probe (one side
run to end-of-input on a structural stack copy), and the three-verdict
fork resolution (take / stop-forced / fork) asked as the forest gate asks
it — on completed VALUES.
"""

from __future__ import annotations

from typing import Any

from lexic.exceptions import LexicError
from lexic.parsing.earley.kernel.forest.ambiguity import same_value
from lexic.parsing.pda.compiler.flatten import (
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_GRP,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
    FlatArm,
    FlatClone,
)
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import (
    KernelCaches,
    admits,
    frames_copy,
    prefix_admits,
    sole_admitted,
)
from lexic.parsing.pda.runtime.build import F_ARM, F_COUNT, F_ENDS, F_I, F_OUT, Step

__all__ = ["Attempting", "sole_admitted"]

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
        return any(admits(char, c, n) for c, n, _re, _sub in clone.attempt[1])
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


def _close_loop(frame: list[Any], i: int, pos: int) -> int:
    """Close the loop at the current count — the driver continues past ``i``."""
    frame[F_COUNT] = 0
    frame[F_I] = i + 1
    frame[F_ENDS][i] = pos
    return i + 1


def _attempt_name(clone: FlatClone) -> str:
    """What an attempt clone builds, by the class its fold constructs."""
    fold = clone.fold
    ctor = getattr(fold, "ctor", None) if fold is not None else None
    return getattr(ctor, "__name__", "") or "(transparent)"


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
    trace: list[Step] | None
    _caches: KernelCaches

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """Provided by the kernel — push (or inline) ``clone``'s frame."""
        raise NotImplementedError

    def _drive(self, floor: int = 0) -> None:
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
        (:func:`~lexic.parsing.pda.compiler.lower._rest_clone`) runs from the
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
        if k > OP_GRP:  # OP_ISLAND / OP_FAIL — no (end, values) to fork-probe
            if self._stop_viable(arm, i, char):
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable"
                )
            return self._attempt_island(frame, arm, i, pos)
        got = self._attempt_run(arm.payloads[i], pos)
        if got is None or got[0] == pos:
            return _close_loop(frame, i, pos)
        cls = self._beyond_class(arm, i, char)
        if self._caches.probing:
            # Inside a probe boundaries resolve GREEDILY by class — probes
            # never nest. The terminator class (a MANDATORY item anywhere up
            # the live chain wants the char) prefers stop; the chain class
            # takes. Either way the probe's outcome becomes a SAMPLED path
            # (uncertain).
            if cls == _ADMITS_HARD:
                self._caches.uncertain = True
                return _close_loop(frame, i, pos)
            if cls == _ADMITS:
                self._caches.uncertain = True
        elif cls in (_ADMITS, _ADMITS_HARD):
            verdict = self._fork_verdict(arm, i, pos, got)
            if verdict == _STOP_FORCED:
                return _close_loop(frame, i, pos)
            if verdict == _FORKED:
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable"
                )
        end, values = got
        self._sink_for(frame, arm, i).extend(values)
        frame[F_COUNT] += 1
        self.pos = end
        return i

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
        for idx, (chars, negated, prefix, sub) in enumerate(entries):
            if not admits(char, chars, negated):
                continue
            if prefix is not None and not prefix_admits(self.text, pos, prefix):
                continue
            best = self._attempt_run(sub, pos)
            if best is not None:
                winner = idx
                break
        if best is None:
            raise PdaFail(f"attempt: no arm matches at {pos}")
        self._attempt_audit(entries[winner + 1 :], pos, best[0], follow)
        out.extend(best[1])
        if self.trace is not None:
            self.trace.append(
                Step(
                    "attempt", _attempt_name(clone), pos, best[0], f"entry {winner} won"
                )
            )
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
        for chars, negated, prefix, sub in rest:
            if not admits(char, chars, negated):
                continue
            if prefix is not None and not prefix_admits(self.text, pos, prefix):
                continue
            other = self._attempt_run(sub, pos)
            if other is None:
                continue
            alt = other[0]
            if alt == end:
                raise PdaFail(
                    f"attempt at {pos}: two arms span [{pos}, {end}) — "
                    "a value question for the gated engine"
                )
            if follow.has(self.text[alt : alt + 1]):
                raise PdaFail(
                    f"attempt at {pos}: arm choice spans two ends ({alt}, {end}) "
                    "and the alternative could compose"
                )

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
