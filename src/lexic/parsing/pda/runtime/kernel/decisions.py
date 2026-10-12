"""The attempt/probe method group — ``PdaKernel``'s decision half.

Shed from the kernel by the file-size rule as a host class the kernel
inherits: the group reads and writes the cursor's own state (``pos``,
``stack``, ``_caches``), so its members stay methods — the two entries the
driver calls (:meth:`Attempting.attempt`,
:meth:`Attempting.attempt_iteration`) are the group's public surface. The class
carries no slots of its own — every attribute it reads is declared by the kernel.

What a both-viable boundary resolves to — take, stop-forced or fork, asked
as the forest gate asks it, on completed VALUES — is
:mod:`~lexic.parsing.pda.runtime.kernel.verdicts`'s, whose host class this one
extends.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from lexic.exceptions import LexicError
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    OP_FAIL,
    OP_ISLAND,
)
from lexic.parsing.pda.compiler.specs import IslandPayload
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import composes
from lexic.parsing.pda.runtime.build import (
    Frame,
)
from lexic.parsing.pda.runtime.islands import IslandEnds
from lexic.parsing.pda.runtime.kernel.verdicts import Verdicts
from lexic.parsing.pda.runtime.matchers import REST_ADMITS, REST_ADMITS_HARD

__all__ = ["Attempting", "claim"]


class Attempting[Carry](Verdicts[Carry]):
    """The attempt/probe methods, hosted for the kernel to inherit.

    Declares the cursor lanes it writes and the driver methods it re-enters
    beyond what :class:`Verdicts` declares; :meth:`attempt` and
    :meth:`attempt_iteration` are the entries the driver calls.
    """

    __slots__ = ()

    text: str
    pos: int

    def _enter(self, clone: FlatClone[Carry], out: list[Carry]) -> bool:
        """Provided by the kernel — push (or inline) ``clone``'s frame."""
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
            if self._stop_viable(arm, i, pos):
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable",
                    pos,
                )
            return self._attempt_island(frame, arm, i, pos)
        try:
            got = self._attempt_run(arm.payloads[i], pos, pos)
        except IslandEnds as two:
            if two.root is not arm.payloads[i] or two.pos != pos:
                raise
            got = self._iteration_ends(two, arm, i, pos)
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

    def _stop_viable(self, arm: FlatArm, i: int, pos: int) -> bool:
        """Whether the boundary char is viable BEYOND another iteration —
        the island branch's trigger (:meth:`_beyond_class` in truth form)."""
        return self._beyond_class(arm, i, pos) in (REST_ADMITS, REST_ADMITS_HARD)

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
        it commits: a second success on the SAME span with a different value is
        a value question for the gated engine, and one on a DIFFERENT span
        whose next character the rule's continuation accepts is a carving the
        decider ranks against the winner (:meth:`_kept_arm`).

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
        self._settle_arm(got, self._attempt_audit(clone, ran + 1, got), out)

    def _settle_arm(
        self,
        won: tuple[int, list[Carry]],
        rivals: list[tuple[int, list[Carry]]] | None,
        out: list[Carry],
    ) -> None:
        """Commit an audited attempt: the winner, or the arm the decider keeps
        among it and its ``rivals`` (:meth:`_kept_arm`), spliced into ``out``
        with the cursor past it."""
        if rivals is not None:
            won = self._kept_arm(won, rivals, out)
        out.extend(won[1])
        self.pos = won[0]

    def _kept_arm(
        self,
        won: tuple[int, list[Carry]],
        rivals: list[tuple[int, list[Carry]]],
        out: list[Carry],
    ) -> tuple[int, list[Carry]]:
        """An attempt's winning arm against the admitted arms that end
        elsewhere and could compose, as ``(end, values)``: the one the decider
        keeps (:meth:`_kept_pick`), each arm a side as an island's completion
        is (:meth:`_extent_side`), at the reference the attempt runs for.

        Two rivals ending alike with different values are a value question;
        and no side can be built where no item of the top frame owns ``out``,
        where the run is not over the whole document (a delegate's sub-run,
        whose root may end anywhere in the island's window, or a truncated
        text: :meth:`RunScope.whole`), or inside a side where :meth:`_nests`
        allows no verdict.

        :raises ProbeFork: In each of those cases, and when the verdict forks:
            the gated engine answers.
        """
        pos = self.pos
        picks = {won[0]: won[1]}
        for end, values in rivals:
            held = picks.setdefault(end, values)
            if not same_value(held, values):
                raise value_question(pos, end)
        k = self._descent_item(out)
        kept = None
        if k >= 0 and self._caches.scope.whole():
            if not self._caches.probing or self._nests():
                ordered = [(end - pos, picks[end]) for end in sorted(picks)]
                kept = self._kept_pick(ordered, partial(self._extent_side, k))
        if kept is None:
            raise ProbeFork(
                f"attempt at {pos}: arm choice spans {sorted(picks)} "
                "and the alternatives could compose",
                pos,
            )
        return pos + kept[0], kept[1]

    def _attempt_audit(
        self,
        clone: FlatClone[Carry],
        first: int,
        won: tuple[int, list[Carry]],
        got: tuple[int, list[Carry]] | None = None,
    ) -> list[tuple[int, list[Carry]]] | None:
        """Audit a winner against the later admitted entries before its caller
        commits it: refuse what the gated engine must decide, and return the
        entries that end elsewhere and could compose, for the decider to rank
        against the winner (:meth:`_kept_arm`) — ``None`` when there are none.

        Runs with the cursor at the attempt position. Each audited entry's
        sub-run is wrapped in a record of the audit (:data:`Audit`), the one
        state a fork inside it cannot read off the stack — in a program that
        can fork (``sub_root``); elsewhere nothing reads one.

        :param clone: The attempt clone whose entry ``won``.
        :param first: The first entry still to audit.
        :param won: The winner's ``(end, values)``.
        :param got: The outcome of entry ``first - 1``, already run — how a
            boundary side resumes an audit it was forked inside; the live
            audit passes none.
        :returns: The rivals, as ``(end, values)``, or ``None``.
        :raises ProbeFork: As :meth:`_contest` raises.
        """
        pos = self.pos
        entries = clone.attempt[1]
        rivals: list[tuple[int, list[Carry]]] | None = None
        if got is not None and self._contest(entries[first - 1][-1], won, got, clone):
            rivals = [got]
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
            if got is not None and self._contest(sub, won, got, clone):
                rivals = [got] if rivals is None else [*rivals, got]
        return rivals

    def _contest(
        self,
        sub: FlatClone[Carry],
        won: tuple[int, list[Carry]],
        got: tuple[int, list[Carry]],
        clone: FlatClone,
    ) -> bool:
        """Whether ``sub``'s success ``got`` is a rival of the winner ``won``,
        both ``(end, values)`` from the attempt position at the cursor: one
        that ends elsewhere and could compose is, for the decider to rank; one
        that cannot compose is no reading at all, and one on the winner's span
        with the winner's value changes nothing.

        :raises ProbeFork: A success on the SAME span with a different value,
            or one that overshoots yet derives the winner's span too — a value
            question the gated engine decides. Undecidable, not a miss: an
            enclosing attempted iteration re-raises it rather than reading it
            as its own arm failing, which would close the loop and commit.
        """
        pos = self.pos
        end, alt = won[0], got[0]
        if alt == end:
            if same_value(got[1], won[1]):
                return False
            raise value_question(pos, end)
        if alt > end and self._spans_exactly(sub, pos, end):
            raise value_question(pos, end)
        return composes(clone.attempt[0], self.text, alt)

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
        whole, scope = self.text, self._caches.scope
        cut, scope.cut = scope.cut, True
        self.text = whole[:end]
        try:
            bounded = self._attempt_run(sub, pos, -2)
        finally:
            self.text, scope.cut = whole, cut
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
        except ProbeFork as fork:
            # Undecidable is NOT failure: swallowing it as this arm's miss
            # would let a later arm commit what the gated engine may refuse.
            if isinstance(fork, IslandEnds):
                claim(fork, holder, sub)
            raise
        except PdaFail:
            island = self._stolen_at(floor)
            if island is None:
                return None
        except LexicError:
            return None
        finally:
            if len(self.stack) > floor:  # a completed drive left none above
                del self.stack[floor:]
            self.pos = saved_pos
        try:
            return self._stolen_back(island, pos)
        except IslandEnds as two:  # the island asked for the run is its outcome
            claim(two, None, sub)
            raise

    def _stolen_at(self, floor: int) -> IslandPayload | None:
        """The island to ask for a sub-run that missed, when its root is a
        rule matched item by item whose own extent proof declines: the miss
        may be a loop taking what the rest of its arm needed, so it is no
        more the rule's answer than a match would be."""
        if len(self.stack) <= floor:
            return None
        take = self.stack[floor].clone.longest
        return take.island if take is not None and take.steals else None

    def _stolen_back(
        self, island: IslandPayload, pos: int
    ) -> tuple[int, list[Carry]] | None:
        """The rule's island at ``pos``, as the sub-run's outcome — ``None``
        when it derives nothing there."""
        saved_pos, self.pos = self.pos, pos
        holder: list[Carry] = []
        try:
            self._island(island, holder)
            return self.pos, holder
        except ProbeFork:
            raise
        except PdaFail:
            return None
        finally:
            self.pos = saved_pos


def value_question(pos: int, end: int) -> ProbeFork:
    """The refusal of two arms over ``[pos, end)`` that build different values."""
    return ProbeFork(
        f"attempt at {pos}: two arms span [{pos}, {end}) — "
        "a value question for the gated engine",
        pos,
    )


def claim(two: IslandEnds, holder: list[Any] | None, sub: FlatClone) -> None:
    """Mark ``two`` the whole outcome of the attempt sub-run of ``sub`` when it
    was asked straight into that run's ``holder`` (``None``: asked for the run
    itself)."""
    if holder is None or two.sink is holder:
        two.root = sub
