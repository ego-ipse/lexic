"""Tests for lexic.parsing.pda.runtime.kernel.decisions — the attempt/probe
decision half of ``PdaKernel``.

``Attempting``'s methods read the live kernel cursor's state (``pos``,
``stack``, ``_caches``) and are exercised end to end through real parses in
``tests/unit/lexic/parsing/pda/test_group_attempt.py`` and the parity suite;
this file targets the module's cursor-free pure helpers directly: the
per-item/per-clone admission tests, the arm-rest walk, FOLLOW composability,
and the loop-close bookkeeping.
"""

from __future__ import annotations

from typing import Any

from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.runtime.build import F_COUNT, F_ENDS, F_I
from lexic.parsing.pda.runtime.kernel.decisions import (
    _ADMITS_HARD,
    _ASCEND,
    _DEAD,
    _arm_rest_scan,
    _close_loop,
    _composes,
    _item_admits,
)
from tests.unit.lexic.parsing.pda.compiler.test_clones import only_arm, pda_from_text

MIXED = 'root ::= "a"? mid [0-9]\nmid ::= "m"\n'


def test_item_admits_a_literal_only_its_own_character():
    """A literal item admits only its exact character."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 0, "a") is True
    assert _item_admits(arm, 0, "z") is False


def test_item_admits_never_admits_the_empty_string():
    """An empty lookahead character never admits, regardless of item kind."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 0, "") is False


def test_item_admits_a_charclass_by_membership():
    """A char class item admits by set membership."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 2, "5") is True
    assert _item_admits(arm, 2, "x") is False


def test_item_admits_delegates_a_clone_reference_to_clone_admits():
    """A clone-reference item defers to the target clone's own admission."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 1, "m") is True
    assert _item_admits(arm, 1, "z") is False


def test_arm_rest_scan_reports_admits_hard_for_a_mandatory_item():
    """From item 0, item 1 (the mandatory ``mid`` clone) admits ``'m'`` —
    settling the walk before item 2 is even reached."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _arm_rest_scan(arm, 0, "m") == (_ADMITS_HARD, False)


def test_arm_rest_scan_reports_dead_when_the_mandatory_item_refuses():
    """A mandatory item refusing the char kills the stop side."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _arm_rest_scan(arm, 0, "5") == (_DEAD, False)


def test_arm_rest_scan_ascends_past_the_arms_final_item():
    """Scanning past the arm's own end yields _ASCEND for the enclosing frame."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _arm_rest_scan(arm, arm.n - 1, "q") == (_ASCEND, False)


def test_composes_is_true_at_end_of_input():
    """End of input always composes — nothing follows to contradict it."""
    follow = CharSet.from_chars("x")
    assert _composes(follow, "abc", 3) is True


def test_composes_checks_the_next_character_against_follow():
    """A next character inside FOLLOW composes; one outside it does not."""
    follow = CharSet.from_chars("x")
    assert _composes(follow, "axb", 1) is True
    assert _composes(follow, "ayb", 1) is False


def test_close_loop_resets_count_advances_i_and_records_the_end():
    """The frame's loop-close bookkeeping: count reset, ``i`` advanced, end recorded."""
    frame: list[Any] = [None] * 9
    frame[F_COUNT] = 5
    frame[F_ENDS] = [None, None, None]
    result = _close_loop(frame, 1, 42)
    assert result == 2
    assert frame[F_COUNT] == 0
    assert frame[F_I] == 2
    assert frame[F_ENDS][1] == 42
