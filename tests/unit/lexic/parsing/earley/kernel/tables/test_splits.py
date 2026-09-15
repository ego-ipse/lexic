"""Tests for lexic.parsing.earley.kernel.tables.splits — which slot owns the
text between two adjacent nullable slots.

``leftmost_chain`` is reached through ``atoms.predecessor_chain`` on every
real parse (``atoms.py`` is not itself owed a unit file — it is exercised
deeply by the parity and roundtrip suites); this file pins ``is_arm_choice``
directly and confirms the leftmost-owns-the-text policy end to end through a
real compiled grammar with two adjacent nullable slots.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.earley.kernel.tables.atoms import KLink
from lexic.parsing.earley.kernel.tables.splits import (
    ChainSpec,
    canonical_indices,
    dominant,
    is_arm_choice,
)


def test_is_arm_choice_is_false_when_every_family_names_the_same_arm():
    """A SPLIT: one child arm reached over different spans — not an ambiguity."""
    bucket: list[KLink] = [(0, 0, 5), (0, 0, 3)]
    code_choice = (7, 7, 7, 7, 7, 7)  # both families' children resolve to arm 7
    assert not is_arm_choice(bucket, bits=1, code_choice=code_choice)


def test_is_arm_choice_is_true_when_families_name_different_arms():
    """A structural choice: two families whose children resolve to DIFFERENT
    authored arms — the refusal's business, not the split policy's."""
    bucket: list[KLink] = [(0, 0, 2), (0, 0, 8)]
    code_choice = (9, 0, 3)  # child 2 -> index 0 -> arm 9; child 8 -> index 2 -> arm 3
    assert is_arm_choice(bucket, bits=1, code_choice=code_choice)


def test_is_arm_choice_treats_a_non_packed_terminal_child_by_its_own_type():
    """A scan/payload child (not a packed handle) is its own arm identity —
    two families with a plain-typed child of the same type name one arm."""
    bucket: list[KLink] = [(0, 0, "leaf"), (0, 0, "other")]
    assert not is_arm_choice(bucket, bits=1, code_choice=())


def test_leftmost_slot_owns_the_text_between_two_adjacent_nullable_repeats():
    """The module's own worked scenario: two adjacent ``[a]*`` slots over
    ``"aa"`` split with nothing said about which owns it — the FIRST slot
    takes as much as it can."""
    cg = compile_text(
        "root ::= p q\np ::= [a]*\nq ::= [a]*\n", cache_key="splits-leftmost"
    )
    model = cg.parse("aa")
    assert model.dump() == {"p": {"value": "aa"}, "q": {"value": ""}}


BITS = 4
"""A small packing tier for hand-built charts: item = (code << 4) | origin."""


def _item(code: int, origin: int) -> int:
    """The packed item for a dotted position at ``code`` starting at ``origin``."""
    return (code << BITS) | origin


def _key(code: int, origin: int, end: int) -> int:
    """The packed handle for that item, ending at ``end``."""
    return (_item(code, origin) << BITS) | end


def _spec(code_choice: tuple[int, ...] = ()) -> ChainSpec:
    """A chain spec over a hand-built link table, with dot 0 as the bottom."""
    return ChainSpec(0, BITS, code_choice)


def _bottomed(*keys: int) -> dict[int, list[KLink]]:
    """Link table where each of ``keys`` steps to the one dot-0 key."""
    return {key: [(_item(0, 0), 0, "bottom")] for key in keys}


def test_dominant_takes_the_larger_end_when_the_chains_meet_at_once():
    """Two families whose predecessors share a chain decide on their own end."""
    spec = _spec()
    far: KLink = (_item(1, 0), 6, "x")
    near: KLink = (_item(1, 0), 2, "y")
    links = _bottomed(_key(1, 0, 6), _key(1, 0, 2))

    assert dominant(links, near, far, spec) is far
    assert dominant(links, far, near, spec) is far


def test_dominant_decides_at_the_deepest_difference_not_the_shallowest():
    """The rule maximises from the LEFT: the deeper boundary outranks the wider.

    ``wide`` ends at 9 where ``deep`` ends at 5 — but one step down, ``wide``'s
    chain sits at 1 and ``deep``'s at 3. The deeper pair differs, so it decides,
    and the family that is wider higher up loses.
    """
    spec = _spec()
    wide: KLink = (_item(2, 0), 9, "x")
    deep: KLink = (_item(2, 0), 5, "y")
    links: dict[int, list[KLink]] = {
        _key(2, 0, 9): [(_item(1, 0), 1, "a")],
        _key(2, 0, 5): [(_item(1, 0), 3, "a")],
        **_bottomed(_key(1, 0, 1), _key(1, 0, 3)),
    }

    assert dominant(links, wide, deep, spec) is deep
    assert dominant(links, deep, wide, spec) is deep


def test_dominant_reads_a_multi_family_predecessor_as_the_reader_does():
    """The case a walk through ``bucket[0]`` gets wrong.

    ``through_p1``'s predecessor holds two families: the first recorded ends at
    2, and the one the reader descends into ends at 6. ``through_p2``'s
    predecessor is a singleton ending at 3. So the deepest boundary reads 6
    against 3 and ``through_p1`` wins — where a walk stepping through the
    first-recorded family reads 2 against 3 and crowns the other one.

    On a forest that keeps every derivation this is the ordinary case: a
    predecessor bucket with more than one family is exactly what a split IS,
    and the first of them is not the rule's answer.
    """
    spec = _spec()
    through_p1: KLink = (_item(2, 0), 5, "x")
    through_p2: KLink = (_item(2, 0), 7, "y")
    links: dict[int, list[KLink]] = {
        _key(2, 0, 5): [(_item(1, 0), 2, "c"), (_item(1, 0), 6, "c")],
        _key(2, 0, 7): [(_item(1, 0), 3, "c")],
        **_bottomed(_key(1, 0, 2), _key(1, 0, 6), _key(1, 0, 3)),
    }

    assert dominant(links, through_p1, through_p2, spec) is through_p1
    assert dominant(links, through_p2, through_p1, spec) is through_p1


def test_dominant_prefers_a_live_chain_over_a_dead_one():
    """A family whose chain does not reach the bottom cannot be the answer."""
    spec = _spec()
    live: KLink = (_item(1, 0), 4, "x")
    dead: KLink = (_item(1, 0), 7, "y")
    links = _bottomed(_key(1, 0, 4))  # nothing recorded under the 7 chain

    assert dominant(links, dead, live, spec) is live
    assert dominant(links, live, dead, spec) is live


def test_canonical_indices_keeps_one_family_per_arm_in_arm_order():
    """The reader's view of a mixed key: each arm once, by first appearance.

    ``code_choice`` sends the first child to arm 9 and the other two to arm 5,
    so the bucket names two arms with the second carved twice. Arm 5 keeps the
    carving the split rule names — the one ending at 6 — and arm 9 stays where
    it first appeared.
    """
    spec = _spec(code_choice=(0, 5, 9))
    bucket: list[KLink] = [
        (_item(1, 0), 2, _key(2, 0, 0)),
        (_item(1, 0), 6, _key(1, 0, 0)),
        (_item(1, 0), 3, _key(1, 0, 0)),
    ]
    links = _bottomed(_key(1, 0, 2), _key(1, 0, 6), _key(1, 0, 3))

    assert canonical_indices(links, bucket, spec) == [0, 1]


def test_canonical_indices_leaves_a_single_arm_bucket_with_its_maximum():
    """One arm carved three ways collapses to the carving the rule names."""
    spec = _spec(code_choice=(0, 5))
    child = _key(1, 0, 0)
    bucket: list[KLink] = [
        (_item(1, 0), 2, child),
        (_item(1, 0), 9, child),
        (_item(1, 0), 5, child),
    ]
    links = _bottomed(_key(1, 0, 2), _key(1, 0, 9), _key(1, 0, 5))

    assert canonical_indices(links, bucket, spec) == [1]
