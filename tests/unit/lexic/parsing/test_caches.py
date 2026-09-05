"""Tests for ``lexic.parsing.caches`` — the identity-memo registry itself.

Pins the four verbs (``memo``, ``adopt``, ``track``, ``release``) and the two
test seams (``reset_caches``, ``cached_entries``) directly, with synthetic
owners and memos so the behaviour is exercised without a real grammar. The
artefact-level pins (a real ``CompiledGrammar`` driving the same machinery
end to end) live beside the existing artefact tests in
``tests/unit/lexic/compile/test_artifact.py``.
"""

from __future__ import annotations

import gc
import threading

import pytest

from lexic.parsing.caches import (
    _ADOPTED,
    _CLAIMED,
    adopt,
    cached_entries,
    memo,
    release,
    reset_caches,
    track,
)


def _fresh_owner() -> threading.Event:
    """A distinct, weak-referenceable stand-in for a real artefact."""
    return threading.Event()


@pytest.fixture(autouse=True)
def _clean_registry():
    """Every test starts and ends on an empty registry.

    ``memo()`` registrations are permanent (the module docstring says so:
    appended at import time, drained but never removed) — a test-registered
    dict stays in ``_MEMOS`` for the rest of the process, contributing zero
    entries once cleared. That is harmless: the isolation this fixture buys
    is over ENTRIES, not registrations.
    """
    reset_caches()
    yield
    reset_caches()


def test_memo_hands_the_dict_straight_back() -> None:
    """The registered dict IS the caller's dict — no wrapping."""
    entries: dict[int, str] = {}
    assert memo(entries) is entries


def test_a_registered_memos_entries_are_counted() -> None:
    """cached_entries sums every registered memo's length."""
    entries = memo({})
    entries[1] = "x"
    entries[2] = "y"
    assert cached_entries() == 2


def test_release_drops_only_entries_a_dropped_identity_owns() -> None:
    """A tuple key's owner position names which entries an id release drops."""
    entries = memo({}, 0)
    kept = object()
    dropped = object()
    entries[(id(dropped), "a")] = 1
    entries[(id(kept), "b")] = 2
    release((id(dropped),))
    assert entries == {(id(kept), "b"): 2}


def test_release_on_a_bare_key_memo_drops_by_direct_identity() -> None:
    """``ids=()`` means the key itself IS the identity (no tuple wrapper).

    The two objects are held in locals, exactly as the test above holds them.
    ``id()`` is only unique among objects that are alive AT THE SAME TIME, so
    ``id(object())`` names an address that is free again on the next line —
    and CPython hands it straight back to the following allocation. That is
    not a subtle risk: it made this test fail on every GitHub run while
    passing locally, because the two builds recycle addresses differently.
    """
    entries = memo({})
    dropped = object()
    kept = object()
    entries[id(dropped)] = "released"
    entries[id(kept)] = "kept"
    release((id(dropped),))
    assert entries == {id(kept): "kept"}


def test_track_binds_release_to_the_owners_collection() -> None:
    """Dropping a tracked owner and collecting it drains its own entries."""
    entries = memo({}, 0)
    mine = _fresh_owner()
    entries[(id(mine), "k")] = "v"
    track(mine, mine)
    del mine
    gc.collect()
    assert not entries


def test_a_second_claimant_does_not_steal_an_already_claimed_identity() -> None:
    """First-claimant-wins: the SECOND ``track()`` call on a shared identity
    is a no-op, so releasing the second (shorter-lived) owner leaves the
    first owner's entries alone."""
    entries = memo({}, 0)
    shared = object()
    long_lived = _fresh_owner()
    short_lived = _fresh_owner()
    entries[(id(shared), "k")] = "v"

    track(long_lived, shared)
    assert id(shared) in _CLAIMED
    track(short_lived, shared)  # already claimed by long_lived — skipped

    del short_lived
    gc.collect()
    assert entries == {(id(shared), "k"): "v"}  # survives the short release
    assert id(shared) in _CLAIMED  # still claimed — by long_lived

    del long_lived
    gc.collect()
    assert not entries


def test_adopt_expands_release_transitively() -> None:
    """A chain adopted under a root drains fully when the root releases,
    with no site needing to know the ultimate owner."""
    entries = memo({}, 0)
    top = _fresh_owner()
    mid = object()
    leaf = object()
    entries[(id(top), "root")] = "r"
    entries[(id(mid), "mid")] = "m"
    entries[(id(leaf), "leaf")] = "l"

    adopt(id(top), mid)
    adopt(id(mid), leaf)
    track(top, top)

    del top
    gc.collect()
    assert not entries


def test_adopt_does_not_release_an_unadopted_sibling() -> None:
    """Only the adopted chain drains — an unrelated entry survives."""
    entries = memo({}, 0)
    top = _fresh_owner()
    derived = object()
    unrelated = object()
    entries[(id(top), "root")] = "r"
    entries[(id(derived), "derived")] = "d"
    entries[(id(unrelated), "unrelated")] = "u"

    adopt(id(top), derived)
    track(top, top)

    del top
    gc.collect()
    assert entries == {(id(unrelated), "unrelated"): "u"}


def test_releasing_a_child_clears_it_from_every_other_owners_record() -> None:
    """A jointly adopted identity leaves no record behind when it retires.

    The engine adopts one object under two owners — a thread's replica lives
    under the grammar it was minted for AND is released on its own when that
    thread exits. Without the sweep, the surviving owner keeps one dead ``id``
    per released child for its whole life: a slow leak in the bookkeeping that
    exists to prevent leaks, and a recycled address that later reads as owned.
    """
    entries = memo({}, 0)
    long_lived = _fresh_owner()
    child = object()
    grandchild = object()
    entries[(id(grandchild), "grandchild")] = "g"

    adopt(id(long_lived), child)
    adopt(id(child), grandchild)
    release((id(child),))

    assert not entries, "the child's own chain should have drained"
    assert id(child) not in _ADOPTED.get(id(long_lived), set())


def test_the_surviving_owner_still_releases_what_it_kept() -> None:
    """The sweep removes the retired child only — siblings still drain."""
    entries = memo({}, 0)
    long_lived = _fresh_owner()
    retired = object()
    kept = object()
    entries[(id(kept), "kept")] = "k"

    adopt(id(long_lived), retired, kept)
    release((id(retired),))
    assert entries == {(id(kept), "kept"): "k"}

    track(long_lived, long_lived)
    del long_lived
    gc.collect()
    assert not entries


def test_reset_caches_empties_every_registered_memo_and_bookkeeping() -> None:
    """The test seam wipes entries, adoption edges and claims alike."""
    entries_a = memo({}, 0)
    entries_b = memo({})
    mine = _fresh_owner()
    entries_a[(id(mine), "k")] = "v"
    entries_b[id(mine)] = "v"
    adopt(id(mine), object())
    track(mine, mine)

    reset_caches()

    assert not entries_a
    assert not entries_b
    assert cached_entries() == 0
    assert not _ADOPTED
    assert not _CLAIMED


def test_release_tolerates_a_concurrent_pop_during_the_sweep() -> None:
    """``release`` sweeps a private copy, so a key vanishing mid-sweep (as a
    concurrent writer might do) is silently tolerated rather than raising."""
    entries = memo({}, 0)
    owner = object()
    entries[(id(owner), "a")] = 1
    entries[(id(owner), "b")] = 2
    entries.pop((id(owner), "a"))  # simulate the concurrent drop
    release((id(owner),))
    assert not entries
