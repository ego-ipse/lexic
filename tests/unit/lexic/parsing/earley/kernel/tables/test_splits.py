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
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice


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
