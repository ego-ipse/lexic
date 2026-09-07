"""Tests for lexic.parsing.product.state — parse-local builders and transactions.

The module's own stated contract is that rollback undoes EXACTLY what
happened since a mark, in constant-size steps, and that a keep-last mapping
duplicate can overwrite an entry INSERTED BEFORE the live mark — the one case
a naive "pop the last insert" rollback would get wrong. Both are exercised
directly, along with the three ways a transaction API can be misused: closing
marks out of LIFO order, and an unknown duplicate policy.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import SemanticVerdict, UnsupportedConstructError
from lexic.parsing.product.state import (
    MAPPING_INSERT,
    MAPPING_REPLACE,
    SEQUENCE_APPEND,
    ParseState,
    ProductMark,
)

_REFUSE = 0
_FIRST = 1
_LAST = 2

_VERDICT = SemanticVerdict(sort="duplicate-key", words="repeated key 'x'")


def test_mutation_kind_constants_are_pinned():
    """The reversible-mutation codes rollback dispatches on, exact values."""
    assert (SEQUENCE_APPEND, MAPPING_INSERT, MAPPING_REPLACE) == (1, 2, 3)


def test_product_mark_field_order():
    """ProductMark is (mutations, sequences, mappings, verdicts, depth)."""
    mark = ProductMark(mutations=1, sequences=2, mappings=3, verdicts=4, depth=5)
    assert tuple(mark) == (1, 2, 3, 4, 5)


# ── sequence lane ────────────────────────────────────────────────────────


def test_sequence_round_trips_in_append_order():
    """A sequence accumulator reads back exactly what it appended, in order."""
    state = ParseState[int]()
    handle = state.begin_sequence()
    state.append_sequence(handle, 1)
    state.append_sequence(handle, 2)
    state.append_sequence(handle, 3)
    assert state.finish_sequence(handle) == (1, 2, 3)


def test_two_sequences_are_independent_lanes():
    """Two occurrence handles never share a builder."""
    state = ParseState[str]()
    first = state.begin_sequence()
    second = state.begin_sequence()
    state.append_sequence(first, "a")
    state.append_sequence(second, "x")
    state.append_sequence(first, "b")
    assert state.finish_sequence(first) == ("a", "b")
    assert state.finish_sequence(second) == ("x",)


def test_sequence_rollback_undoes_exactly_what_happened_after_the_mark():
    """A mark's rollback removes only appends logged after it, none before."""
    state = ParseState[int]()
    handle = state.begin_sequence()
    state.append_sequence(handle, 1)
    mark = state.mark()
    state.append_sequence(handle, 2)
    state.append_sequence(handle, 3)
    state.rollback(mark)
    assert state.finish_sequence(handle) == (1,)


def test_sequence_commit_keeps_everything_the_transaction_did():
    """A committed transaction's appends survive, unlike a rolled-back one."""
    state = ParseState[int]()
    handle = state.begin_sequence()
    mark = state.mark()
    state.append_sequence(handle, 1)
    state.commit(mark)
    assert state.finish_sequence(handle) == (1,)


def test_nested_rollback_leaves_the_outer_transactions_appends_intact():
    """Rolling back an inner mark cannot touch what an outer one already did."""
    state = ParseState[int]()
    handle = state.begin_sequence()
    outer = state.mark()
    state.append_sequence(handle, 1)
    inner = state.mark()
    state.append_sequence(handle, 2)
    state.rollback(inner)
    state.commit(outer)
    assert state.finish_sequence(handle) == (1,)


# ── mapping lane: duplicate policies ─────────────────────────────────────


def test_mapping_round_trips_in_insertion_order():
    """Distinct keys read back in the order they were first inserted."""
    state = ParseState[int]()
    handle = state.begin_mapping()
    state.insert_mapping(handle, "a", 1, _VERDICT)
    state.insert_mapping(handle, "b", 2, _VERDICT)
    assert state.finish_mapping(handle) == (("a", 1), ("b", 2))


def test_refuse_duplicate_policy_records_the_verdict_and_keeps_the_first_value():
    """The default policy (0) does not mutate the entry — it records a refusal."""
    state = ParseState[int]()
    handle = state.begin_mapping(duplicates=_REFUSE)
    state.insert_mapping(handle, "a", 1, _VERDICT)
    state.insert_mapping(handle, "a", 2, _VERDICT)
    assert state.finish_mapping(handle) == (("a", 1),)
    assert state.verdicts == (_VERDICT,)


def test_first_duplicate_policy_keeps_the_first_value_silently():
    """Keep-first mutates nothing and records no verdict — a silent no-op."""
    state = ParseState[int]()
    handle = state.begin_mapping(duplicates=_FIRST)
    state.insert_mapping(handle, "a", 1, _VERDICT)
    state.insert_mapping(handle, "a", 2, _VERDICT)
    assert state.finish_mapping(handle) == (("a", 1),)
    assert not state.verdicts


def test_last_duplicate_policy_overwrites_in_place_keeping_position():
    """Keep-last replaces the VALUE but not the key's original position."""
    state = ParseState[int]()
    handle = state.begin_mapping(duplicates=_LAST)
    state.insert_mapping(handle, "a", 1, _VERDICT)
    state.insert_mapping(handle, "b", 9, _VERDICT)
    state.insert_mapping(handle, "a", 2, _VERDICT)
    assert state.finish_mapping(handle) == (("a", 2), ("b", 9))
    assert not state.verdicts


def test_last_duplicate_rollback_restores_an_entry_overwritten_from_before_the_mark():
    """The sharpest case the module names: keep-last can overwrite an entry
    inserted BEFORE the live mark, which a bare "pop the newest insert" undo
    cannot restore — MAPPING_REPLACE exists to log the OLD entry instead."""
    state = ParseState[int]()
    handle = state.begin_mapping(duplicates=_LAST)
    state.insert_mapping(handle, "a", 1, _VERDICT)  # before any mark
    mark = state.mark()
    state.insert_mapping(handle, "a", 2, _VERDICT)  # overwrites the pre-mark entry
    assert state.finish_mapping(handle) == (("a", 2),)
    state.rollback(mark)
    assert state.finish_mapping(handle) == (("a", 1),)


def test_last_duplicate_rollback_of_a_fresh_insert_removes_it_entirely():
    """A keep-last overwrite of an entry inserted DURING the same transaction
    is an ordinary fresh insert as far as rollback is concerned: gone, not
    reverted to some earlier value, because there is no earlier value."""
    state = ParseState[int]()
    handle = state.begin_mapping(duplicates=_LAST)
    mark = state.mark()
    state.insert_mapping(handle, "a", 1, _VERDICT)
    state.insert_mapping(handle, "a", 2, _VERDICT)  # overwrite within the mark
    state.rollback(mark)
    assert state.finish_mapping(handle) == ()


def test_unknown_duplicate_policy_refuses_rather_than_silently_keeping_first():
    """A policy code this state does not implement is refused by name."""
    state = ParseState[int]()
    handle = state.begin_mapping(duplicates=99)
    state.insert_mapping(handle, "a", 1, _VERDICT)
    with pytest.raises(UnsupportedConstructError, match="unknown duplicate policy"):
        state.insert_mapping(handle, "a", 2, _VERDICT)


# ── transaction discipline ────────────────────────────────────────────────


def test_verdicts_recorded_outside_a_transaction_are_not_touched_by_rollback():
    """record() outside any mark leaves nothing for a later rollback to undo."""
    state = ParseState[int]()
    state.record(_VERDICT)
    handle = state.begin_sequence()
    mark = state.mark()
    state.append_sequence(handle, 1)
    state.rollback(mark)
    assert state.verdicts == (_VERDICT,)


def test_commit_out_of_lifo_order_refuses():
    """Closing an outer mark while an inner one is still live is refused."""
    state = ParseState[int]()
    outer = state.mark()
    state.mark()
    with pytest.raises(UnsupportedConstructError, match="newest first"):
        state.commit(outer)


def test_rollback_out_of_lifo_order_refuses():
    """The same discipline holds for rollback, not only commit."""
    state = ParseState[int]()
    outer = state.mark()
    state.mark()
    with pytest.raises(UnsupportedConstructError, match="newest first"):
        state.rollback(outer)


def test_a_second_transaction_after_the_first_closes_starts_clean():
    """Committing one transaction does not leave stray state for the next."""
    state = ParseState[int]()
    handle = state.begin_sequence()
    first = state.mark()
    state.append_sequence(handle, 1)
    state.commit(first)
    second = state.mark()
    state.append_sequence(handle, 2)
    state.rollback(second)
    assert state.finish_sequence(handle) == (1,)
