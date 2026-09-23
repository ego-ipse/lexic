"""The split decider — which carving of one span a parse keeps, as a VALUE.

:mod:`~lexic.parsing.earley.kernel.tables.splits` works out each family's
CARVING, its boundary vector over the node's authored item sequence, with a
repetition's iterations spliced in and zero-width iterations beyond its minimum
dropped. That is structure, and the same whatever is decided. What a decider
adds is one question, :meth:`Decider.rank`: a total preorder over carvings,
where the maximum wins. Both engines ask it: Earley to choose among a span's
families, and the ambiguity check to find the alternatives that tie with the
chosen one.

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


class Decider(IrNamedTuple[frozenset[str]]):
    """Ranks the carvings of one span; the maximum rank is the one kept.

    A value record: its fields are what it is, so two deciders are equal when
    they are the same kind with the same fields, and a product cached under
    one is found again under the other. A field a future decider adds joins
    that key by being a field.

    :ivar grants: The licence kinds proven for this decider.
    """

    grants: frozenset[str]

    def rank(self, carving: Carving) -> Carving:
        """Where ``carving`` stands in this decider's order: a key whose
        natural order is a total preorder over carvings, maximum kept."""
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        """The same kind of decider, with every field equal."""
        return type(other) is type(self) and tuple.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        """Stated, not inherited: ``tuple`` defines its own, which would
        compare the fields alone."""
        return not self == other

    def __hash__(self) -> int:
        """Consistent with :meth:`__eq__`: the kind and every field."""
        return hash((type(self), tuple(self)))


class LeftmostLongest(Decider):
    """The first slot takes as much as it can, then the next, and so on.

    The rank IS the carving: the lexicographically greatest boundary vector
    from the left wins. Over a repetition this keeps fewer, longer iterations,
    because the first iteration's end is compared first.
    """

    def rank(self, carving: Carving) -> Carving:
        """The carving itself."""
        return carving


LEFTMOST_LONGEST = LeftmostLongest(
    frozenset({SPLIT_GREEDY, ATTEMPT, STOP_SET, NOISE_GREEDY, GREEDY_SPLIT})
)
"""The decider both engines use unless a caller passes another.

It grants the licences proven for it. :data:`STOP_SET` is granted because the
analysis files a stop-set only where its first exit is this order's answer:
the loop runs longest, no text continues both ways two characters deep, or
every carving builds one model. :data:`GREEDY_ARM` owes its exchange proof, so
it is withheld: those sites island instead, and Earley answers."""
