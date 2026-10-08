"""The split decider — which carving of one span a parse keeps, as a VALUE.

:mod:`~lexic.parsing.earley.kernel.tables.splits` works out each family's
CARVING, its boundary vector over the node's authored item sequence, with a
repetition's iterations spliced in and zero-width iterations beyond its minimum
dropped (:func:`carving`). That is structure, and the same whatever is decided.
What a decider adds is one question, :meth:`Decider.slot`: where ONE boundary
stands in its order. A carving's rank is its slots read left to right
(:meth:`Decider.rank`, final), so every decider compares carvings the same way
— on the first boundary that differs — and differs only in how it orders one
boundary. Both engines ask it: Earley to choose among a span's families, and
the ambiguity check to find the alternatives that tie with the chosen one.

A decider also names the licences proven for it (:attr:`Decider.grants`). A
predictive shortcut that commits the split answer without asking, such as a
greedy loop exit, is sound only for a decider whose answer it has been shown to
reproduce, so each shortcut is licensed per decider, by kind — one kind per
kind of shortcut, so a proof for one grants nothing to another.

**What it cannot express.** A rank orders the carvings of ONE node over ONE
fixed span, and the choice recurses top-down into the spans it gives each
child. A rule that is not per node, such as "fewest nodes in the whole tree",
has no such decomposition and is not a decider.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import final

from lexic.ir import IrNamedTuple

SPLIT_GREEDY = "split-greedy"
"""A loop exit licensed because the decider's absorption ends the unit there."""

ATTEMPT = "attempt"
"""A loop's greedy attempted take committed as the decider's split answer."""

STOP_SET = "stop-set"
"""A loop leaves at the first character of a stop set."""

NOISE_GREEDY = "noise-greedy"
"""A noise loop runs greedily through what its stop set would admit."""

GREEDY_SPLIT = "greedy-split"
"""A loop over-eats a soft follower whose split the decider settles."""

GREEDY_ARM = "greedy-arm"
"""An arm is taken greedily over an empty sibling whose follower it starts."""

Carving = tuple[int, ...]
"""A family's boundary vector over one span, left to right."""


def carving(ends: Iterable[int]) -> Carving:
    """A chain's boundaries as a carving: a step ending where the previous one
    did is a zero-width iteration, dropped, so one reading never competes with
    itself plus an empty slot."""
    out: list[int] = []
    for end in ends:
        if not out or end != out[-1]:
            out.append(end)
    return tuple(out)


class Decider(IrNamedTuple[frozenset[str]]):
    """Ranks the carvings of one span; the maximum rank is the one kept.

    A value record: its fields are what it is, so two deciders are equal when
    they are the same kind with the same fields, and a product cached under
    one is found again under the other. A field a future decider adds joins
    that key by being a field.

    A decider states :meth:`slot`; the rank is final. A subclass that redefines
    :meth:`rank` is refused when it is defined, because Earley reads a chain
    one boundary at a time and can honour no order that is not its slots read
    left to right.

    :ivar grants: The licence kinds proven for this decider.
    """

    grants: frozenset[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Refuse a subclass that redefines the final rank."""
        super().__init_subclass__(**kwargs)
        if "rank" in vars(cls):
            raise TypeError(f"{cls.__name__}: a decider states slot(), not rank()")

    def slot(self, end: int) -> int:
        """Where one boundary ending at ``end`` stands: a larger slot ranks
        higher. Strict: two different ends never share a slot."""
        raise NotImplementedError

    @final
    def rank(self, steps: Carving) -> tuple[int, ...]:
        """Where a carving stands in this decider's order: its slots, read left
        to right, compared lexicographically; the maximum is kept."""
        return tuple(map(self.slot, steps))


class LeftmostLongest(Decider):
    """The first slot takes as much as it can, then the next, and so on.

    A boundary's slot IS its end, so the rank is the carving itself: the
    lexicographically greatest boundary vector from the left wins. Over a
    repetition this keeps fewer, longer iterations, because the first
    iteration's end is compared first. The slot is final, and a subclass that
    redefines it is refused: Earley reads this order's levels by their raw
    maximum key, which is this order's choice and no other's — so every
    instance, whatever it grants, may be read that way, and none can be made
    to mean anything else.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Refuse a subclass that redefines the final slot."""
        super().__init_subclass__(**kwargs)
        if "slot" in vars(cls):
            raise TypeError(f"{cls.__name__}: leftmost-longest's slot is final")

    @final
    def slot(self, end: int) -> int:
        """The end itself."""
        return end


LEFTMOST_LONGEST = LeftmostLongest(
    frozenset({SPLIT_GREEDY, ATTEMPT, STOP_SET, NOISE_GREEDY, GREEDY_SPLIT})
)
"""The decider both engines use unless a caller passes another.

It grants the licences proven for it. :data:`STOP_SET` is granted because the
analysis files a stop-set only where its first exit is this order's answer:
the loop runs longest, no text continues both ways two characters deep, or
every carving builds one model. :data:`GREEDY_ARM` owes its exchange proof, so
it is withheld: those sites island instead, and Earley answers."""
