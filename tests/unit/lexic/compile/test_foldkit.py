"""Tests for compile/foldkit.py — the shared authored-transform vocabulary.

The shared idioms every hand-authored surface names by key: the identity
``passthrough``, the ``first_rest`` list collector, and the ``absent_tail``
absent-default tail with its ``ABSENT`` sentinel. ``FOLD_SYMBOLS`` is the
whitelist those keys resolve through.

The pass-through and named-leaf tiers were deleted with the fold vocabulary
they belonged to; what remains here are the tests whose targets survived,
with their assertions unchanged.
"""

from __future__ import annotations

from lexic.compile.foldkit import (
    ABSENT,
    FOLD_SYMBOLS,
    absent_tail,
    first_rest,
    passthrough,
)
from lexic.compile.notation import parse as notation
from lexic.ir import IrNone

# ── the shared idioms — behavior ─────────────────────────────────────────


def test_passthrough_returns_its_argument_unchanged():
    """passthrough is a pure identity function over any value."""
    sentinel = object()
    assert passthrough(sentinel) is sentinel
    assert passthrough("x") == "x"
    assert passthrough(0) == 0
    assert passthrough(None) is None


def test_first_rest_prepends_head_to_tail():
    """first_rest is the head-plus-tail list collector."""
    assert first_rest("a") == ("a",)
    assert first_rest("a", ["b", "c"]) == ("a", "b", "c")
    assert first_rest("a", ()) == ("a",)


def test_absent_tail_returns_the_present_value_including_ir_none():
    """absent_tail returns the keyword value when present — even IrNone."""
    assert absent_tail(v="x") == "x"
    assert absent_tail(v=IrNone) is IrNone  # IrNone is a legitimate argument
    assert absent_tail() is ABSENT  # an empty call is the omitted tail


def test_fold_symbols_is_the_curated_registry():
    """FOLD_SYMBOLS holds only the shared idiom callables."""
    assert FOLD_SYMBOLS["first_rest"] is first_rest
    assert FOLD_SYMBOLS["passthrough"] is passthrough


def test_notation_reuses_the_shared_vocabulary_objects():
    """notation.py consumes foldkit's shared vocab BY IDENTITY, not a copy."""
    assert notation.first_rest is first_rest
