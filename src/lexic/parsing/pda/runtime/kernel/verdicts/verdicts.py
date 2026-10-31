"""The boundary verdict — whether a both-viable attempted boundary takes,
stops or forks, and how the decider ranks two ways it can go.

Shed from :mod:`~lexic.parsing.pda.runtime.kernel.decisions` by the file-size
rule as a host class its :class:`~lexic.parsing.pda.runtime.kernel.decisions.Attempting`
inherits, for the same reason that one is a host class: every member reads and
writes the cursor's own state. A boundary in the live drive is settled by a
live set over its ways (:mod:`.liveset`); a boundary inside one of the set's
readings splits it instead. Each way is a side (:mod:`.sides`), and where two
meet with different values the rank here is what the set asks.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

from lexic.parsing.earley.kernel.tables.decider import LeftmostLongest, carving
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    lands_on,
)
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.admission import (
    Side,
)
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.islands import IslandEnds
from lexic.parsing.pda.runtime.kernel.verdicts.liveset import (
    FORKED,
    STOP_FORCED,
    TAKE,
    LiveSet,
)
from lexic.parsing.pda.runtime.kernel.verdicts.sides import (
    PENDING,
    UNSEEN,
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
    "STOP_FORCED",
    "TAKE",
    "Verdicts",
]


class Verdicts[Carry](LiveSet[Carry]):
    """The boundary-verdict methods, hosted for ``Attempting`` to inherit; the
    kernel surface they read is declared on :class:`~.sides.Sides`, beside the
    lane they write."""

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
        if self._caches.probing:  # inside a reading: it splits, never guesses
            if cls == REST_DEAD or (
                self._caches.scope.whole()
                and stop_side_dead(self.stack, arm, i, self.text, pos)
            ):
                return True  # stopping is dead: taking is forced
            raise self._split(
                [
                    self._side(arm, i, pos, None, self._recording()),
                    self._side(arm, i, pos, got, self._recording()),
                ],
                pos,
            )
        if cls in (REST_ADMITS, REST_ADMITS_HARD):
            return self._fork_verdict(arm, i, pos, got) == TAKE
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
        """A both-viable loop boundary's resolution — :data:`TAKE` or
        :data:`STOP_FORCED` — settled by the live set over its two ways, the
        stop first (:meth:`~.liveset.LiveSet._decide`).

        :param taken: The iteration's ``(end, values)`` (the take side's seed).
        :raises ProbeFork: When the set cannot decide — an island inside a
            reading that no verdict there could settle included, as a plain
            fork, so no handler outside reads it as its own island's ends.
        """
        roots = [
            partial(self._side, arm, i, pos, None),
            partial(self._side, arm, i, pos, taken),
        ]
        try:
            kept = self._decide(roots, True)
        except IslandEnds as two:
            raise ProbeFork(
                f"attempt loop at {pos}: taking and stopping are both viable", pos
            ) from two
        return STOP_FORCED if kept == 0 else TAKE

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
        items = self._pushed_by(
            depth, descending(live) + ([live.i] if iterating(live) else [])
        )
        whole = bool(items) and all(once(live, k) for k in items)
        if len(set(items)) == 1:
            own = self._own_step(stop[6][depth], take[6][depth], items[0])
            if own is not None:
                return own
        elif not whole:
            return FORKED
        return self._child_step(ends, stop[1], whole)

    def _pushed_by(self, depth: int, items: list[int]) -> list[int]:
        """Of ``items`` — a frame just past an exactly-once item with a loop next
        lists both — the one that pushed the frame above it: the item whose
        payload IS that frame's clone, where no other item's payload can land
        on that clone (:func:`~...flatten.lands_on`). Otherwise ``items``
        unchanged."""
        if len(set(items)) < 2 or depth + 1 >= len(self.stack):
            return items
        child, payloads = self.stack[depth + 1].clone, self.stack[depth].arm.payloads
        named = [k for k in set(items) if payloads[k] is child]
        others = [payloads[k] for k in set(items) if k not in named]
        lands = any(isinstance(p, FlatClone) and lands_on(p, child) for p in others)
        return named if len(named) == 1 and not lands else items

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
        whatever the decider's order. Leftmost-longest's slot is the end itself,
        so every end from ``at`` on ranks alike and ``at`` stands for them all;
        any other order is asked at every end the step can reach."""
        if max(ends) >= at:
            return FORKED
        reach = range(at, at + 1 if self._takes_longest() else len(self.text) + 1)
        found = {
            self._kept(*((at_end if end == PENDING else end,) for end in ends))
            for at_end in reach
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
        in, each read as Earley reads a carving: the only place a boundary
        verdict asks the decider. A step here is one node's end and never an
        iteration the carving drops; a step that could be one, an empty
        iteration at a loop that took nothing, forks before it is ranked
        (:meth:`_child_step`)."""
        decide = self.policy.config.decide
        stop_rank = decide.rank(carving(stop, self.pos, (False,) * len(stop)))
        take_rank = decide.rank(carving(take, self.pos, (False,) * len(take)))
        if stop_rank > take_rank:
            return STOP_FORCED
        return TAKE

    def _extent(self, two: IslandEnds, k: int, sink: list[Carry]) -> None:
        """An island whose reference may follow more than one of its
        completions, settled by the boundary verdict and spliced into ``sink``.

        The reference is item ``k`` of the top frame, the cursor at the island,
        and the frame already as the descent left it, so each completion is a
        side: the live stack forked with that completion's value in the item
        and the cursor past it (:meth:`_extent_side`), ranked as
        :meth:`_kept_end` ranks them. Inside a reading of a live set the
        reading splits, one child per completion; never at a reference the top
        frame does not stand in (``k < 0``): the island is then left to whoever
        owns ``sink``.

        :raises IslandEnds: When a verdict forks, or no verdict can be asked.
        :raises Split: Inside a reading.
        """
        if k < 0:
            two.sink = sink
            raise two
        if self._caches.probing:  # inside a set: the reading splits
            raise self._split(
                [
                    self._extent_side(k, end, values, self._recording())
                    for end, values in self._picks(two)
                ],
                self.pos,
            )
        end, values = self._kept_end(two, partial(self._extent_side, k))
        sink.extend(values)
        self.pos += end

    def _iteration_ends(
        self, two: IslandEnds, arm: FlatArm, i: int, pos: int
    ) -> tuple[int, list[Carry]]:
        """An attempted iteration of item ``i`` whose whole sub-run is an
        island with more than one followable completion: each completion is a
        candidate iteration, taken on a side of its own
        (:meth:`_iteration_side`), and the one the verdict keeps is the
        iteration's outcome. Inside a reading of a live set the reading
        splits, one child per completion.

        :returns: The kept iteration's ``(end, values)``.
        :raises IslandEnds: When a verdict forks, or no verdict can be asked.
        :raises Split: Inside a reading.
        """
        if self._caches.probing:  # inside a set: the reading splits
            raise self._split(
                [
                    self._iteration_side((arm, i, pos), end, values, self._recording())
                    for end, values in self._picks(two)
                ],
                pos,
            )
        end, values = self._kept_end(two, partial(self._iteration_side, (arm, i, pos)))
        return pos + end, values

    def _kept_end(
        self, two: IslandEnds, side_of: Callable[..., Side]
    ) -> tuple[int, list[Carry]]:
        """The completion of ``two`` the verdict keeps, as ``(end, values)``,
        each completion a side ``side_of(end, values)`` builds
        (:meth:`_kept_pick`).

        :raises IslandEnds: When a pair's verdict forks.
        """
        kept = self._kept_pick(self._picks(two), side_of)
        if kept is None:
            raise two
        return kept

    def _picks(self, two: IslandEnds) -> list[tuple[int, list[Carry]]]:
        """Each completion of ``two`` as ``(end, values)``, shortest first."""
        picks: list[tuple[int, list[Carry]]] = []
        for tree, end, built in two.ends:
            value = self._island_value(two.name, tree, built)
            picks.append((end, [value.value] if isinstance(value, Completed) else []))
        return picks

    def _kept_pick(
        self, picks: list[tuple[int, list[Carry]]], side_of: Callable[..., Side]
    ) -> tuple[int, list[Carry]] | None:
        """Of several ways one item can end — ``(end, values)``, shortest
        first — the one the verdict keeps, ``None`` when it cannot say.

        Every pick is one way of the live set, the decider's order shortest
        first (:meth:`~.liveset.LiveSet._decide`); a set that cannot decide says
        ``None``, and the caller hands the item to whoever answers it.
        """
        try:
            kept = self._decide(
                [partial(side_of, end, values) for end, values in picks], False
            )
        except ProbeFork:
            return None
        return picks[kept]
