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

from collections.abc import Callable
from functools import partial
from typing import Any

from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.earley.kernel.tables.decider import LeftmostLongest, carving
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
)
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.admission import (
    NESTING_DEPTH,
    Side,
    control_signature,
    pending_values,
    value_shape,
)
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.islands import IslandEnds
from lexic.parsing.pda.runtime.kernel.sides import (
    PENDING,
    UNSEEN,
    Sides,
    descending,
    iterating,
    once,
    recorded,
)
from lexic.parsing.pda.runtime.matchers import (
    REST_ADMITS,
    REST_ADMITS_HARD,
    REST_ASCEND,
    REST_DEAD,
    arm_rest_scan,
    stop_side_dead,
)
from lexic.parsing.product import Completed
from lexic.parsing.product.tree import CompletionResult

__all__ = [
    "FORKED",
    "Makers",
    "STOP_FORCED",
    "TAKE",
    "Verdicts",
]

_LOCKSTEP_ROUNDS = 32
"""How many convergence rounds a boundary gets before the slow path takes it.
A budget, not a correctness knob: running out costs today's two full probes."""

_LOCKSTEP_STEP = 8
"""Characters to advance both sides by when they stand at the same position but
different control states — small, because convergence is usually one element
away and every character driven past it is wasted."""

type Makers = tuple[Callable[..., Side], tuple[object, ...], tuple[object, ...]]
"""How a verdict's two sides are built afresh: a builder, and its arguments for
the stop side and for the take side; the builder takes last whether the side
keeps a ledger (:meth:`Sides._forked`). Plain values, so a verdict that never
ranks pays nothing to carry them (:meth:`Verdicts._made`)."""

TAKE, STOP_FORCED, FORKED = 0, 1, 2
"""A both-viable boundary's resolutions (:meth:`Verdicts._fork_verdict`)."""


_NESTING_BUDGET = 64
"""How many nested verdicts one retry may ask. Past it every boundary left is a
guess, so the retry forks: a document that would cost more goes whole to the
gated engine, as it did before the retry."""


class Verdicts[Carry](Sides[Carry]):
    """The boundary-verdict methods, hosted for ``Attempting`` to inherit; the
    kernel surface they read is declared on :class:`Sides`, beside the lane
    they write."""

    __slots__ = ()

    pos: int

    def _island_value(
        self, name: str, tree: Any, built: CompletionResult[Carry] | None
    ) -> CompletionResult[Carry]:
        """Provided by the kernel — what one island completion splices."""
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
            if cls == REST_DEAD or (
                self._caches.scope.whole()
                and stop_side_dead(self.stack, arm, i, self.text, pos)
            ):
                return True  # stopping is dead: taking is forced, not sampled
            settled = self._nested_verdict(arm, i, pos, got)
            if settled is not None:
                return settled
            # Unsettled inside a probe, a boundary resolves GREEDILY by class.
            # The terminator class (a MANDATORY item anywhere up the live
            # chain wants the char) prefers stop; the chain class takes.
            # Either way the probe's outcome becomes a SAMPLED path
            # (uncertain).
            if cls == REST_ADMITS_HARD:
                self._caches.uncertain = True
                return False
            if cls == REST_ADMITS:
                self._caches.uncertain = True
        elif cls in (REST_ADMITS, REST_ADMITS_HARD):
            try:
                verdict = self._fork_verdict(arm, i, pos, got)
            except IslandEnds:  # an island inside a side: a verdict of its own
                verdict = FORKED
            if verdict == FORKED:
                verdict = self._retried(self._fork_verdict, arm, i, pos, got)
            if verdict == STOP_FORCED:
                return False
            if verdict == FORKED:
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable",
                    pos,
                )
        return True

    def _retried[*Args](self, ask: Callable[[*Args], int], *args: *Args) -> int:
        """A forked verdict asked again, the boundaries inside its sides settled
        by verdicts of their own (:meth:`_nests`).

        Asked only after a fork: a side's guess is what usually forks it, and
        a nested verdict costs a fork per boundary inside a side, so a verdict
        that settles without them never pays for them. The fork it replaces
        would hand the whole document to the gated engine, and does once the
        parse's allowance (:data:`~...admission.PARSE_NESTING`) is spent.
        """
        scope = self._caches.scope
        if not scope.open(_NESTING_BUDGET):
            return FORKED
        try:
            return ask(*args)
        finally:
            scope.close()

    def _nests(self) -> bool:
        """Whether a verdict may be asked inside a side here, spending one of
        the retry's budget if so: only while a forked verdict is asked again
        (:meth:`_retried`), at most :data:`~...admission.NESTING_DEPTH` sides deep, and
        within :data:`_NESTING_BUDGET` nested verdicts. Past either, the
        boundary stays a guess, or an island's extent stays unsettled. Nested
        sides carry the sub-runs the side still has to settle
        (:meth:`_inherited_floors`)."""
        caches = self._caches
        return caches.probing <= NESTING_DEPTH and caches.scope.take()

    def _nested_verdict(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        got: tuple[int, list[Carry]],
    ) -> bool | None:
        """Whether a boundary inside a side takes, settled by a verdict of its
        own where :meth:`_nests` allows one.

        :returns: ``True`` to take, ``False`` to stop, ``None`` when it stays
            a guess.
        """
        if not self._nests():
            return None
        try:
            verdict = self._fork_verdict(arm, i, pos, got)
        except ProbeFork:
            return None  # undecidable inside the side: it stays a guess
        if verdict == TAKE:
            return True
        return False if verdict == STOP_FORCED else None

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
                verdict, seen = arm_rest_scan(frame.arm, frame.suspended(), text, pos)
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
        are ranked by the decider (:meth:`_ranked`). A death or a completion
        either drive reached through a greedy guess (``uncertain``) is the
        guess's as much as the boundary's, so it decides nothing and forks.

        :param taken: The iteration's ``(end, values)`` (the take side's seed).
        :returns: :data:`TAKE` / :data:`STOP_FORCED` / :data:`FORKED`.
        """
        settled = self._lockstep_verdict(arm, i, pos, taken)
        if settled is not None:
            return settled
        stop, stop_unc = self._probe(arm, i, pos, None)
        if stop is None:
            return FORKED if stop_unc else TAKE
        take = self._probe(arm, i, pos, taken)
        return self._compared(stop, stop_unc, take, self._makers(arm, i, pos, taken))

    def _makers(
        self, arm: FlatArm, i: int, pos: int, taken: tuple[int, list[Carry]]
    ) -> Makers:
        """The loop boundary's two sides, stop then take (:data:`Makers`)."""
        return self._side, (arm, i, pos, None), (arm, i, pos, taken)

    @staticmethod
    def _made(makers: Makers, take: bool, record: bool) -> Side:
        """One of a verdict's two sides, built afresh: the take side's when
        ``take``, keeping a ledger when ``record``."""
        build, stop, taken = makers
        return build(*(taken if take else stop), record)

    def _compared(
        self,
        stop: Side,
        stop_unc: bool,
        take: tuple[Side | None, bool],
        makers: Makers,
    ) -> int:
        """Two sides run to the end of input, the stop side complete: a dead
        take forces the stop, one value is a benign split, and two values are
        ranked (:meth:`_ranked`) — unless a drive guessed on the way, when it
        proves nothing and forks.

        :param stop: The completed stop side.
        :param stop_unc: Whether its drive guessed.
        :param take: The take side, ``None`` if it died, and its guess.
        :param makers: The two sides afresh, for the rank.
        """
        done, take_unc = take
        if done is None:
            return FORKED if take_unc else STOP_FORCED
        if stop_unc or take_unc:
            return FORKED
        if same_value(done[3], stop[3]):
            return TAKE
        return self._ranked(makers, -1, (stop, done))

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
          a dead stop side is :data:`TAKE` exactly as before. A REFUSAL there
          is the exception: a completion that refuses reads the values it
          gathered, which differ between the sides, so running the left side's
          remainder says nothing about the right's, and the boundary is
          undecidable (:meth:`_advance` raises :class:`ProbeFork`).
        - **the STOP side dies** — :data:`TAKE`, since the caller tests
          ``stop is None`` first regardless; a dead TAKE side does not settle
          it, turning on the stop side reaching end-of-input, unestablished.

        A death the stop side's own drive reached through a greedy guess, and a
        mid-parse convergence either side's did, decide nothing and fork, as at
        end of input (:meth:`_fork_verdict`).

        No convergence in the budget returns ``None``: the caller runs today's
        comparison. A :class:`ProbeFork` PROPAGATES — undecidable is not death.

        :returns: The verdict, or ``None`` when the long way must decide.
        """
        stop, take = self._side(arm, i, pos, None), self._side(arm, i, pos, taken)
        return self._lockstep(stop, take, self._makers(arm, i, pos, taken))

    def _lockstep(
        self, left: Side | None, right: Side | None, makers: Makers
    ) -> int | None:
        """Advance the stop side and the take side in step until they converge
        (:meth:`_converged`) or one dies, inside the round budget; ``None`` when
        the long way must decide. ``makers`` builds them afresh, for the rank."""
        shape = value_shape(self.stack)
        left_unc = right_unc = False
        for _round in range(_LOCKSTEP_ROUNDS):
            if left is None:
                return FORKED if left_unc else TAKE
            if right is None:
                return None
            target = max(left[1], right[1])
            if left[1] == right[1]:
                if len(left[4]) == len(right[4]) and control_signature(
                    left[0], left[1]
                ) == control_signature(right[0], right[1]):
                    guessed = left_unc or right_unc
                    return self._converged(left, right, shape, guessed, makers)
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
        makers: Makers,
    ) -> int | None:
        """The verdict once both sides share a position and a control state.

        Only the values built SINCE the boundary are compared — ``shape`` is
        the watermark taken there, and both sides inherited everything below it
        from one stack. Sides that converged by COMPLETING hold empty stacks,
        so what they built is in their root outputs, and those are compared.
        Sides whose values differ are ranked (:meth:`_ranked`) — read before
        the common remainder runs, while both ledgers stand at the convergence
        — once that remainder is seen to complete. A guess on the way
        unsettles a rank as it does a mid-parse agreement, and completed sides
        reached through one fork, agreeing or not: the guess may have dropped
        the carving the decider keeps.

        :param guessed: Whether either side's drive guessed on the way here.
        :param makers: The two sides afresh, for the rank.
        """
        if not left[0]:
            if guessed:
                return FORKED
            if same_value(left[3], right[3]):
                return TAKE
            return self._ranked(makers, -1, (left, right))
        if same_value(pending_values(left[0], shape), pending_values(right[0], shape)):
            return FORKED if guessed else TAKE
        ranked = FORKED if guessed else self._ranked(makers, left[1], (left, right))
        done, sampled = self._advance(left, -1, shared=True)
        if done is None:  # the common remainder completes on neither side
            return FORKED if guessed or sampled else TAKE
        return FORKED if sampled else ranked

    def _ranked(self, makers: Makers, at: int, sides: tuple[Side, Side]) -> int:
        """Two sides whose values differ, ranked as the gated engine ranks them
        (:meth:`_rank`): ``sides`` themselves where they kept ledgers, else
        both built again keeping ledgers and driven to ``at`` (``-1``: to the
        end) — exactly where they stood, since outside a retry a drive is a
        function of where it starts and where it stops."""
        if sides[0][5] is not None:
            return self._rank(*sides)
        stop, _guessed = self._advance(self._made(makers, False, True), at)
        take, _guessed = self._advance(self._made(makers, True, True), at)
        if stop is None or take is None:
            return FORKED
        return self._rank(stop, take)

    def _rank(self, stop: Side, take: Side) -> int:
        """Two sides keeping ledgers, ranked as the gated engine ranks them:
        the shallowest frame whose carving differs, at its first differing step.

        Frames the fork copied that completed at one position on both sides
        carve alike — from there on both share a control state, and before the
        fork they share everything — so the first copied depth whose ledger
        entries differ names the step: its parent's step into it
        (:meth:`_ranked_at`). Every copied frame completing alike leaves the
        boundary's own frame: the first of its items to end apart — at a loop
        boundary the loop itself, which ends at the boundary on the stop side —
        and failing that the fork's own step, the island's two ends.

        A node's own steps are compared raw, as Earley compares a chain's
        boundaries: a step that ends where the one before it did stays in the
        vector. Only a repetition's iterations drop a zero-width one
        (:meth:`_ranked_at`). A child whose completion the ledger cannot read —
        a sub-run its caller settled on something else, a closed loop or a
        replacing entry — is ranked by the step its parent recorded instead.
        """
        for depth, (left, right) in enumerate(zip(stop[5] or (), take[5] or ())):
            if left == right and left != UNSEEN:
                continue
            if not depth:
                return FORKED
            return self._ranked_at(depth - 1, stop, take, (left, right))
        ends = zip(stop[6][-1].ends or (), take[6][-1].ends or ())
        steps = [(a, b) for a, b in ends if a != b]
        if steps:
            return (
                FORKED if min(steps[0]) < 0 else self._kept(*map(tuple, zip(steps[0])))
            )
        mine, theirs = stop[7], take[7]
        if len(mine) != 2 or len(theirs) != 2:
            return FORKED
        (k, stop_end), (_k, take_end) = mine, theirs
        if not once(self.stack[-1], k) and not self._takes_longest():
            return FORKED
        return self._kept((stop_end,), (take_end,))

    def _ranked_at(
        self, depth: int, stop: Side, take: Side, ends: tuple[int, int]
    ) -> int:
        """The rank at the copied frame standing at ``depth``, whose child
        completed at ``ends`` on the two sides (``-2``: unreadable) and at one
        place above.

        The step is the frame's item's own end where both sides passed the
        item and recorded it: a loop's end, or an optional's; Earley's loop is
        a node, so a loop's end is compared first. An exactly-once reference
        records none, so its step is its child's end. A loop that ends alike
        leaves its iterations, the forked one the first that differs — unless
        the stop side's may be zero-width, an iteration at a boundary whose
        loop had taken nothing, which the loop's carving drops. A child still
        open on one side at a convergence ends somewhere in the sides' common
        future (:meth:`_kept_open`). The item is read as a side's floors are
        (:func:`descending`, :func:`iterating`); one the frame may not stand in
        alone, an item passed on one side only, or a step neither record shows,
        forks.
        """
        live = self.stack[depth]
        items = descending(live) + ([live.i] if iterating(live) else [])
        whole = bool(items) and all(once(live, k) for k in items)
        if len(set(items)) == 1:
            own = self._own_step(stop[6][depth], take[6][depth], items[0])
            if own is not None:
                return own
        elif not whole:
            return FORKED
        return self._child_step(ends, stop[1], whole)

    def _own_step(self, mine: Frame[Carry], theirs: Frame[Carry], k: int) -> int | None:
        """The rank by item ``k``'s own recorded end on the two copies of one
        frame, or ``None`` when both recorded it alike, or neither passed it,
        and its child decides."""
        if (mine.i > k) != (theirs.i > k):
            return FORKED
        step = recorded(mine, k), recorded(theirs, k)
        if mine.i <= k or step[0] == step[1]:
            return None
        return FORKED if min(step) < 0 else self._kept(*map(tuple, zip(step)))

    def _child_step(self, ends: tuple[int, int], at: int, whole: bool) -> int:
        """The rank by where the child completed on the two sides — an
        iteration of a loop unless ``whole`` — at a convergence at ``at``."""
        if UNSEEN in ends or ends == (PENDING, PENDING):
            return FORKED
        if not whole and not self._takes_longest():
            return FORKED
        if not whole and ends[0] == self.pos and not self.stack[-1].count:
            return FORKED
        if PENDING in ends:
            return self._kept_open(ends, at)
        return self._kept((ends[0],), (ends[1],))

    def _kept_open(self, ends: tuple[int, int], at: int) -> int:
        """The rank of two steps one of which is still open (``PENDING``) at a
        convergence at ``at``: it ends at ``at`` or later, and the sides share
        what follows. Settled only where it cannot end where the other step
        did, and every end it can reach ranks the same way against it —
        whatever the decider's order."""
        if max(ends) >= at:
            return FORKED
        found = {
            self._kept(*((at_end if end == PENDING else end,) for end in ends))
            for at_end in range(at, len(self.text) + 1)
        }
        return found.pop() if len(found) == 1 else FORKED

    def _takes_longest(self) -> bool:
        """Whether the decider is leftmost-longest: the one order whose
        repetitions are ranked here by where their first differing iteration
        ends — Earley reads ``X+`` as ``X | X X+``, and has been shown to answer
        that way only for it. Under any other decider those repetitions fork,
        and the gated engine answers."""
        return isinstance(self.policy.config.decide, LeftmostLongest)

    def _kept(self, stop: tuple[int, ...], take: tuple[int, ...]) -> int:
        """The side the decider keeps, by the rank of the steps the two differ
        in — each a carving, a zero-width step dropped, as Earley ranks a
        node's: the only place a boundary verdict asks the decider."""
        decide = self.policy.config.decide
        if decide.rank(carving(stop)) > decide.rank(carving(take)):
            return STOP_FORCED
        return TAKE

    def _extent(self, two: IslandEnds, k: int, sink: list[Carry]) -> None:
        """An island whose reference may follow more than one of its
        completions, settled by the boundary verdict and spliced into ``sink``.

        The reference is item ``k`` of the top frame, the cursor at the island,
        and the frame already as the descent left it, so each completion is a
        side: the live stack forked with that completion's value in the item
        and the cursor past it (:meth:`_extent_side`), ranked as
        :meth:`_kept_end` ranks them. Inside a side only where :meth:`_nests`
        allows a verdict there, and never at a reference the top frame does not
        stand in (``k < 0``): the island is then left to whoever owns ``sink``.

        :raises IslandEnds: When a verdict forks, or no verdict can be asked.
        """
        if k < 0 or (self._caches.probing and not self._nests()):
            two.sink = sink
            raise two
        end, value = self._kept_end(two, partial(self._extent_side, k))
        if isinstance(value, Completed):
            sink.append(value.value)
        self.pos += end

    def _iteration_ends(
        self, two: IslandEnds, arm: FlatArm, i: int, pos: int
    ) -> tuple[int, list[Carry]]:
        """An attempted iteration of item ``i`` whose whole sub-run is an
        island with more than one followable completion: each completion is a
        candidate iteration, taken on a side of its own
        (:meth:`_iteration_side`), and the one the verdict keeps is the
        iteration's outcome. Inside a side only where :meth:`_nests` allows.

        :returns: The kept iteration's ``(end, values)``.
        :raises IslandEnds: When a verdict forks, or no verdict can be asked.
        """
        if self._caches.probing and not self._nests():
            raise two
        end, value = self._kept_end(two, partial(self._iteration_side, (arm, i, pos)))
        return pos + end, [value.value] if isinstance(value, Completed) else []

    def _kept_end(
        self, two: IslandEnds, side_of: Callable[..., Side]
    ) -> tuple[int, CompletionResult[Carry]]:
        """The completion of ``two`` the verdict keeps, each completion a side
        ``side_of(end, value)`` builds.

        Completions meet in pairs, the one kept so far as the stop side against
        the next longer, each pair driven and ranked as an attempted loop's
        sides are; the rank is one order over completed parses, so the last
        one kept is the decider's.

        :raises IslandEnds: When a pair's verdict forks.
        """
        picks = [
            (end, self._island_value(two.name, tree, built))
            for tree, end, built in two.ends
        ]
        kept = picks[0]
        for pick in picks[1:]:
            try:
                verdict = self._pair(side_of, kept, pick)
            except IslandEnds:
                if self._caches.probing:
                    raise
                verdict = FORKED  # an island inside a side: a verdict of its own
            if verdict == FORKED and not self._caches.probing:
                verdict = self._retried(self._pair, side_of, kept, pick)
            if verdict == FORKED:
                raise two
            if verdict == TAKE:
                kept = pick
        return kept

    def _pair(
        self,
        side_of: Callable[..., Side],
        stop: tuple[int, CompletionResult[Carry]],
        take: tuple[int, CompletionResult[Carry]],
    ) -> int:
        """The verdict between two completions, the shorter standing as the
        stop side: in step first, else each run to the end of input and
        compared."""
        makers: Makers = side_of, stop, take
        verdict = self._lockstep(side_of(*stop, False), side_of(*take, False), makers)
        if verdict is not None:
            return verdict
        done, unc = self._advance(self._made(makers, False, False), -1)
        if done is None:
            return FORKED if unc else TAKE
        taken = self._advance(self._made(makers, True, False), -1)
        return self._compared(done, unc, taken, makers)
