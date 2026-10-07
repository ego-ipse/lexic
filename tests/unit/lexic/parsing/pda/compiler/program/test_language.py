"""Tests for lexic.parsing.pda.compiler.program.language — which text arms an
item-wise match can miss, and the automaton that reads them instead."""

from __future__ import annotations

import pytest

from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.program.gating import KWindowSelect
from lexic.parsing.pda.compiler.program.language import (
    STATE_CAP,
    ForcedEnd,
    ScanTally,
    language_of,
    needs_language,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    BUILD_SEQ,
    DISPATCH_EMPTY,
    BUILD_VALUE_STR,
    GATE_ATTEMPT,
    GATE_KWIN,
    GATE_STOP,
    OP_CC1,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
    OP_REF,
)
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.errors import ProbeFork
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone

_A = (frozenset("a"), False)
_A_SEMI = (frozenset("a;"), False)
_STOP_NOTHING = (frozenset(), False)


def _run_then_class(gate_kind: int = GATE_ATTEMPT, gate=(_A, _STOP_NOTHING)):
    """``[a]* [a;]`` — the run can take the one character the class needs."""
    return flat_arm(
        2,
        kinds=(OP_LIT, OP_CC1),
        payloads=("a", _A_SEMI),
        los=(0, 1),
        his=(-1, 1),
        gate_kinds=(gate_kind, GATE_STOP),
        gate_data=(gate, _A_SEMI),
    )


def test_a_run_that_can_take_its_successors_character_needs_the_language() -> None:
    """``[a]*`` before ``[a;]``: on ``a`` the run takes it and the class has
    nothing left, though ``a`` is in the arm's language."""
    assert needs_language(_run_then_class())


def test_a_stop_gated_run_is_judged_by_its_own_set() -> None:
    """A stop gate takes on its set: one holding ``a`` steals, one without
    it cannot."""
    assert needs_language(_run_then_class(GATE_STOP, _A))
    assert not needs_language(_run_then_class(GATE_STOP, (frozenset("b"), False)))


def test_disjoint_neighbours_keep_the_item_wise_match() -> None:
    """``[a]* ";"``: the run can never take the semicolon."""
    arm = flat_arm(
        2,
        kinds=(OP_LIT, OP_LIT1),
        payloads=("a", ";"),
        los=(0, 1),
        his=(-1, 1),
        gate_kinds=(GATE_ATTEMPT, GATE_STOP),
        gate_data=((_A, _STOP_NOTHING), _STOP_NOTHING),
    )
    assert not needs_language(arm)


def test_an_optional_last_item_is_the_continuations_question() -> None:
    """``";" ";"?``: nothing of the arm follows the optional, so whatever it
    could steal belongs to the rule's continuation, which its gate carries."""
    arm = flat_arm(
        2,
        kinds=(OP_LIT1, OP_LIT),
        payloads=(";", ";"),
        los=(1, 0),
        his=(1, 1),
        gate_kinds=(GATE_STOP, GATE_ATTEMPT),
        gate_data=(_STOP_NOTHING, ((frozenset(";"), False), (frozenset("a"), False))),
    )
    assert not needs_language(arm)


def test_a_stealing_item_inside_a_referenced_text_clone_marks_the_arm() -> None:
    """The test runs at every depth: the run sits in a referenced clone."""
    inner = flat_clone(
        BUILD_VALUE_STR,
        wide_selectors=None,
        selectors=((frozenset("a;"), False, _run_then_class()),),
        default=None,
    )
    inner.name = "inner"
    arm = flat_arm(
        1,
        kinds=(OP_REF,),
        payloads=(inner,),
        los=(1,),
        his=(1,),
        gate_kinds=(GATE_STOP,),
        gate_data=(_STOP_NOTHING,),
    )
    assert needs_language(arm)


def test_the_automaton_finds_every_end_the_greedy_run_misses() -> None:
    """``[a]* [a;]`` accepts after every character of ``aa;``, and after the
    single ``a`` the item-wise match fails on."""
    lang = language_of(_run_then_class())
    assert lang is not None
    assert lang.scan("aa;", 0, 99) == ([1, 2, 3], 3)
    assert lang.scan("a", 0, 99) == ([1], 1)
    assert lang.scan("b", 0, 99) == ([], 0)


def test_a_bounded_repeat_and_an_optional_are_counted_exactly() -> None:
    """``"ab"{1,2} [a;]``: ends after one or two ``ab``, each followed by
    exactly one class character."""
    arm = flat_arm(
        2,
        kinds=(OP_LIT, OP_CC1),
        payloads=("ab", _A_SEMI),
        los=(1, 1),
        his=(2, 1),
        gate_kinds=(GATE_ATTEMPT, GATE_STOP),
        gate_data=(((frozenset("a"), False), _STOP_NOTHING), _A_SEMI),
    )
    lang = language_of(arm)
    assert lang is not None
    assert lang.scan("ababa;", 0, 99) == ([3, 5], 5)


def test_a_structure_building_clone_has_no_text_language() -> None:
    """A clone that builds a record is not read by its text."""
    record = flat_clone(
        BUILD_SEQ, selectors=((frozenset("a"), False, _run_then_class()),), default=None
    )
    record.name = "record"
    arm = flat_arm(1, kinds=(OP_REF,), payloads=(record,), los=(1,), his=(1,))
    assert language_of(arm) is None


def test_an_island_has_no_text_language() -> None:
    """An island is decided elsewhere; its language is not known here."""
    arm = flat_arm(1, kinds=(OP_ISLAND,), payloads=(None,), los=(1,), his=(1,))
    assert language_of(arm) is None


def test_a_recursive_clone_has_no_automaton() -> None:
    """A clone reached again on its own path is not regular here."""
    loop = flat_clone(BUILD_VALUE_STR, wide_selectors=None, default=None)
    loop.name = "loop"
    arm = flat_arm(1, kinds=(OP_REF,), payloads=(loop,), los=(1,), his=(1,))
    loop.selectors = ((frozenset("a"), False, arm),)
    assert language_of(arm) is None


def test_an_automaton_past_the_state_cap_is_refused() -> None:
    """A repeat wide enough to pass the cap keeps the item-wise matcher."""
    arm = flat_arm(
        1,
        kinds=(OP_LIT,),
        payloads=("a",),
        los=(0,),
        his=(STATE_CAP,),
        gate_kinds=(GATE_ATTEMPT,),
        gate_data=((_A, _STOP_NOTHING),),
    )
    assert language_of(arm) is None


# ── the forced end ────────────────────────────────────────────────────────


def _forced(follow: str) -> ForcedEnd:
    """``[a]* [a;]`` judged against a FOLLOW of ``follow``'s characters."""
    lang = language_of(_run_then_class())
    assert lang is not None
    return ForcedEnd(lang, CharSet.from_chars(*follow))


def test_only_the_end_the_follow_admits_is_taken() -> None:
    """``[a]* [a;]`` accepts after each character of ``aa;``; with only ``,``
    able to follow the rule, the ends before an ``a`` or a ``;`` are dead."""
    with ScanTally(4):
        got = _forced(",").match("aa;,", 0)
    assert got is not None and got.end() == 3


def test_two_viable_ends_bail() -> None:
    """Where ``a`` may follow too, ``a`` and ``aa`` both survive on ``aa``: a
    choice the forced end does not make."""
    with ScanTally(2), pytest.raises(ProbeFork, match="both could compose"):
        _forced("a").match("aa", 0)


def test_no_viable_end_is_a_miss_not_a_bail() -> None:
    """An arm that accepts nowhere a follower can start did not derive here."""
    with ScanTally(2):
        assert _forced(",").match("ab", 0) is None


def test_an_arm_without_an_automaton_bails_rather_than_match_item_by_item() -> None:
    """Marked, but past the state cap: the forced end refuses outright — the
    item-wise match is the one known to miss text."""
    with ScanTally(1), pytest.raises(ProbeFork, match="cannot be read"):
        ForcedEnd(None, CharSet.from_chars(",")).match("a", 0)


def test_a_scan_outside_any_parse_bails() -> None:
    """The account belongs to a parse; a scan no parse owns does not run."""
    with pytest.raises(ProbeFork, match="cannot be read"):
        _forced(",").match("a,", 0)


def test_the_rescan_account_is_the_parses_and_only_the_parses() -> None:
    """One parse re-reading one character again and again spends its budget
    of four times the document's length, and bails on the sixth scan; six
    parses doing the same once each never touch each other's account."""
    forced = _forced("")
    with ScanTally(1):
        for _ in range(5):
            got = forced.match("a", 0)
            assert got is not None and got.end() == 1
        with pytest.raises(ProbeFork, match="rescan budget"):
            forced.match("a", 0)
    for _ in range(6):
        with ScanTally(1):
            got = forced.match("a", 0)
            assert got is not None and got.end() == 1


def test_a_nested_account_joins_the_parse_already_open() -> None:
    """A sub-run that opens an account inside a parse charges the parse's."""
    forced = _forced("")
    with ScanTally(1):
        for _ in range(5):
            with ScanTally(1):
                forced.match("a", 0)
        with pytest.raises(ProbeFork, match="rescan budget"):
            forced.match("a", 0)


# ── dispatch targets ──────────────────────────────────────────────────────


def _text_leaf(char: str):
    """A value clone matching exactly ``char``."""
    arm = flat_arm(
        1,
        kinds=(OP_LIT1,),
        payloads=(char,),
        los=(1,),
        his=(1,),
        gate_kinds=(GATE_STOP,),
        gate_data=(_STOP_NOTHING,),
    )
    leaf = flat_clone(
        BUILD_VALUE_STR,
        wide_selectors=None,
        selectors=((frozenset(char), False, arm),),
        default=None,
    )
    leaf.name = f"leaf-{char}"
    return leaf


def _through(clone: FlatClone) -> FlatArm:
    """An arm that is one reference to ``clone``."""
    return flat_arm(
        1,
        kinds=(OP_REF,),
        payloads=(clone,),
        los=(1,),
        his=(1,),
        gate_kinds=(GATE_STOP,),
        gate_data=(_STOP_NOTHING,),
    )


def test_a_wide_dispatch_reads_its_targets_through_its_selection() -> None:
    """A dispatch selecting by window keeps its targets in that selection, not
    in its lead-character selectors; reading only those made the language
    empty, which accepted nothing on ``a``."""
    wide = flat_clone(
        BUILD_DISPATCH,
        wide_selectors=KWindowSelect(
            (((((frozenset("a"), False),),), _text_leaf("a")),)
        ),
        selectors=(),
        default=None,
    )
    wide.name = "wide"
    lang = language_of(_through(wide))
    assert lang is not None
    assert lang.scan("a", 0, 9) == ([1], 1)


def test_a_dispatch_with_an_empty_default_accepts_nothing_too() -> None:
    """The empty-arm default is the empty string, not a missing target."""
    dispatch = flat_clone(
        BUILD_DISPATCH,
        wide_selectors=None,
        selectors=((frozenset("b"), False, _text_leaf("b")),),
        default=DISPATCH_EMPTY,
    )
    dispatch.name = "maybe-b"
    lang = language_of(_through(dispatch))
    assert lang is not None
    assert lang.scan("b", 0, 9) == ([0, 1], 1)


def test_a_dispatch_target_that_is_not_a_clone_has_no_automaton() -> None:
    """Vocabulary the automaton does not model refuses; it never becomes an
    empty language."""
    odd = flat_clone(
        BUILD_DISPATCH,
        wide_selectors=None,
        selectors=((frozenset("a"), False, "not a clone"),),
        default=None,
    )
    odd.name = "odd"
    assert language_of(_through(odd)) is None


def test_a_separable_k_window_loop_is_not_marked() -> None:
    """A granted ``k``-window gate takes only where its take and exit windows
    separate at ``k``, so it cannot take what the rest starts with — even
    where the run's FIRST meets the rest's, as ``[a]*`` before ``[a;]``."""
    assert not needs_language(_run_then_class(GATE_KWIN, ()))
