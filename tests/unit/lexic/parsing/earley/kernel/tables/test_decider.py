"""Tests for ``lexic.parsing.earley.kernel.tables.decider`` — the split decider.

A decider is a VALUE with one question, ``rank``, whose natural order must be
a total preorder over carvings (the maximum is kept), and a set of licences.
The order is pinned on hand-built carvings, in the shape ``splits`` hands
them over: zero-width iterations beyond a repetition's minimum already
dropped.
"""

from __future__ import annotations

from itertools import product

import pytest

from lexic.parsing.earley.kernel.tables.decider import (
    ATTEMPT,
    GREEDY_ARM,
    GREEDY_SPLIT,
    LEFTMOST_LONGEST,
    NOISE_GREEDY,
    SPLIT_GREEDY,
    STOP_SET,
    Carving,
    Decider,
    LeftmostLongest,
)

CARVINGS: tuple[Carving, ...] = (
    (6,),
    (4, 6),
    (2, 4, 6),
    (2, 6),
    (3, 6),
    (3, 3, 6),
    (0, 6),
    (6, 6),
)


class _ShortestFirst(Decider):
    """A second decider built only from the interface: the reverse order."""

    def rank(self, carving: Carving) -> Carving:
        """Each boundary negated, so the shortest first slot ranks highest."""
        return tuple(-end for end in carving)


DECIDERS = (LEFTMOST_LONGEST, _ShortestFirst(frozenset()))


@pytest.mark.parametrize("decider", DECIDERS, ids=["leftmost-longest", "shortest"])
def test_rank_is_a_total_preorder(decider: Decider) -> None:
    """Reflexive, total and transitive over every pair and triple."""
    ranks = [decider.rank(one) for one in CARVINGS]
    again = [decider.rank(one) for one in CARVINGS]
    assert all(first <= second for first, second in zip(ranks, again, strict=True))
    assert all(a <= b or b <= a for a, b in product(ranks, repeat=2))
    assert all(a <= c for a, b, c in product(ranks, repeat=3) if a <= b <= c)


def test_one_long_first_iteration_beats_two_short_ones() -> None:
    """``a;a;a;`` read as one ``sec`` ``(6,)`` against two ``(4, 6)``: the
    first slot's end is compared first, and 6 beats 4."""
    assert LEFTMOST_LONGEST.rank((6,)) > LEFTMOST_LONGEST.rank((4, 6))
    assert max(CARVINGS, key=LEFTMOST_LONGEST.rank) == (6, 6)
    assert max(CARVINGS[:4], key=LEFTMOST_LONGEST.rank) == (6,)


def test_a_kept_zero_width_iteration_would_rank_below_its_dropped_carving() -> None:
    """``(3, 3, 6)`` keeps an empty iteration at 3; with it dropped, the same
    reading is ``(3, 6)``. They must not compete as two readings, so the
    carving drops it, and a carving that kept it ranks lower."""
    assert LEFTMOST_LONGEST.rank((3, 6)) > LEFTMOST_LONGEST.rank((3, 3, 6))


def test_the_leftmost_order_decides_on_the_first_boundary_that_differs() -> None:
    """Later boundaries matter only when every earlier one is equal."""
    assert LEFTMOST_LONGEST.rank((3, 6)) > LEFTMOST_LONGEST.rank((2, 6))
    assert LEFTMOST_LONGEST.rank((2, 6)) > LEFTMOST_LONGEST.rank((2, 4, 6))


def test_another_decider_is_only_another_value() -> None:
    """The same carvings under the reverse rank keep the other extreme."""
    assert max(CARVINGS[:4], key=_ShortestFirst(frozenset()).rank) == (2, 4, 6)


def test_leftmost_longest_grants_only_what_is_proven_for_it() -> None:
    """Every kind proven for this order is granted; the greedy arm take still
    owes its proof, so it is not."""
    proven = {SPLIT_GREEDY, ATTEMPT, STOP_SET, NOISE_GREEDY, GREEDY_SPLIT}
    assert proven == LEFTMOST_LONGEST.grants
    assert GREEDY_ARM not in LEFTMOST_LONGEST.grants


def test_a_decider_without_licences_grants_none() -> None:
    """The same rank with nothing proven: every shortcut must ask instead."""
    bare = LeftmostLongest(frozenset())
    assert SPLIT_GREEDY not in bare.grants
    assert bare.rank((4, 6)) == LEFTMOST_LONGEST.rank((4, 6))


def test_deciders_are_values() -> None:
    """Equal by kind and fields, so a product cached under one is found under
    an equal one; different licences are a different key."""
    same = LeftmostLongest(frozenset(LEFTMOST_LONGEST.grants))
    assert same == LEFTMOST_LONGEST and hash(same) == hash(LEFTMOST_LONGEST)
    assert LeftmostLongest(frozenset()) != LEFTMOST_LONGEST


def test_another_kind_with_the_same_fields_is_another_decider() -> None:
    """Records compare as tuples; a decider must not, or two orders granting
    the same licences would share one cached product."""
    other = _ShortestFirst(LEFTMOST_LONGEST.grants)
    assert other != LEFTMOST_LONGEST
    assert hash(other) != hash(LEFTMOST_LONGEST)


class _Windowed(LeftmostLongest):
    """A decider with a parameter of its own, as a future one might have. A
    record subclass states its whole field list."""

    grants: frozenset[str]
    width: int


def test_every_field_is_part_of_the_key() -> None:
    """A parameter a decider adds is part of what it is."""
    assert _Windowed(frozenset(), 2) != _Windowed(frozenset(), 3)
    assert _Windowed(frozenset(), 2) == _Windowed(frozenset(), 2)


def test_the_base_decider_ranks_nothing() -> None:
    """``rank`` is the one question a decider must answer for itself."""
    with pytest.raises(NotImplementedError):
        Decider(frozenset()).rank((1,))
