"""Tests for ``lexic.parsing.earley.kernel.tables.decider`` — the split decider.

A decider is a VALUE with one question, ``slot`` — where one boundary stands —
whose final ``rank`` reads a carving's slots left to right, a total preorder
over carvings (the maximum is kept), and a set of licences.
The order is pinned on hand-built carvings, in the shape ``splits`` hands
them over: zero-width iterations beyond a repetition's minimum already
dropped.
"""

from __future__ import annotations

from itertools import product

import pytest

from lexic.parsing.earley.kernel.tables.decider import (
    ATTEMPT,
    GREEDY_SPLIT,
    LEFTMOST_LONGEST,
    NOISE_GREEDY,
    SCAN_SKIP,
    SPLIT_GREEDY,
    STOP_SET,
    Carving,
    Decider,
    LeftmostLongest,
    carving,
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

    def slot(self, end: int) -> int:
        """The end negated, so the shortest first slot ranks highest."""
        return -end


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
    """Every kind proven for this order is granted, and nothing else."""
    proven = {SPLIT_GREEDY, ATTEMPT, STOP_SET, NOISE_GREEDY, GREEDY_SPLIT, SCAN_SKIP}
    assert proven == LEFTMOST_LONGEST.grants


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
    """Two orders granting the same licences are two deciders, so they never
    share one cached product. Records are class-aware; their hashes may
    coincide, which a cache tolerates, so the hash is not asserted apart."""
    other = _ShortestFirst(LEFTMOST_LONGEST.grants)
    assert other != LEFTMOST_LONGEST
    assert LEFTMOST_LONGEST != other
    assert len({other: 1, LEFTMOST_LONGEST: 2}) == 2


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


def _negated(_self: Decider, value: tuple[int, ...]) -> tuple[int, ...]:
    """A redefinition the classes below try to install: the reverse order."""
    return tuple(-end for end in value)


def test_a_leftmost_longest_subclass_cannot_reorder_it() -> None:
    """A subclass that redefined the rank passed every ``isinstance`` check
    while Earley read its chain levels by raw maximum and its children by the
    new order: ``x+`` over ``aaa`` came out ``X('aa'), X('a')``, which neither
    order gives. Redefining the rank, or leftmost-longest's slot, is now
    refused when the class is defined. The classes are built by ``type`` —
    the static checker already rejects such a subclass, and this pins that the
    runtime does too."""
    with pytest.raises(TypeError, match="slot"):
        type("_Reranked", (LeftmostLongest,), {"rank": _negated})
    with pytest.raises(TypeError, match="final"):
        type("_Reslotted", (LeftmostLongest,), {"slot": _negated})


def test_any_decider_states_slots_and_never_its_rank() -> None:
    """The rank is a decider's slots read left to right, for every decider:
    the one comparison Earley can honour level by level."""
    with pytest.raises(TypeError, match="slot"):
        type("_Ranked", (Decider,), {"rank": _negated})
    shortest = _ShortestFirst(frozenset())
    assert shortest.rank((2, 4, 6)) == (-2, -4, -6)
    assert LEFTMOST_LONGEST.rank((2, 4, 6)) == (2, 4, 6)


def test_a_carving_drops_an_empty_iteration_beyond_the_minimum() -> None:
    """A droppable step that ends where the one before it did is an iteration
    the repetition's minimum does not need; dropped, the reading cannot
    compete with itself plus an empty iteration. The first step is measured
    from the start, so it is dropped too."""
    assert carving((3, 3, 6), 0, (True, True, True)) == (3, 6)
    assert not carving((0, 0, 0), 0, (True, True, True))
    assert not carving((), 0, ())
    assert carving((2, 4, 6), 0, (True, True, True)) == (2, 4, 6)


def test_a_carving_keeps_a_slot_or_a_needed_iteration_that_takes_nothing() -> None:
    """An authored slot, or an iteration within the minimum, is a step even
    when it takes nothing: ``x{2,}`` over ``a`` as ``("", "a")`` is two steps,
    and only the decider says which of its carvings is kept."""
    assert carving((0, 1), 0, (False, False)) == (0, 1)
    assert carving((1, 1), 0, (False, True)) == (1,)
    assert carving((3, 3, 6), 0, (False, False, False)) == (3, 3, 6)


def test_a_decider_grants_all_of_a_set_only_when_it_grants_each_kind() -> None:
    """What a program compiled under ``used`` may run for this decider."""
    assert LEFTMOST_LONGEST.grants_all(frozenset({SPLIT_GREEDY, ATTEMPT}))
    assert LEFTMOST_LONGEST.grants_all(frozenset())
    assert not LEFTMOST_LONGEST.grants_all(frozenset({"unproven"}))
    assert not _ShortestFirst(frozenset()).grants_all(frozenset({ATTEMPT}))
