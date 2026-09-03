"""Tests for lexic.parsing.pda.compiler.program.product — the flat clone bake.

The module's own three claims, each pinned directly: absence is coded on
``lo`` (0 when a capture may be absent, 1 otherwise) rather than a quantifier;
TEXT is one mode whose flat code (``M_TEXT``/``M_GTEXT``) carries the absence
question; and the build mode comes off the completion record — a transparent
clone (no routine), a pass-through (construction is None, a real source), and
a value-string construction (``construction.matched``) are three different
shapes read off the SAME record, never a parallel ``kind`` string.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.compiler.program.flatten import (
    FlatClone,
    no_construction,
    no_fast_construction,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_TEXT,
    M_VALUE,
)
from lexic.parsing.pda.compiler.program.product import bake_product_build
from lexic.parsing.product.abi.construction import Construction
from lexic.parsing.product.abi.records import CaptureMode
from lexic.parsing.product.routines import RuleRoutine


def _clone() -> FlatClone:
    return FlatClone.__new__(FlatClone)


def _routine(modes, slots, n_items, source, construction) -> RuleRoutine:
    return RuleRoutine(7, tuple(modes), tuple(slots), n_items, source, construction)


class _Rec:
    def __init__(self, a=None, b=None):
        self.a, self.b = a, b

    @classmethod
    def fast_construct(cls):
        return (lambda values: cls(*values), {}, ("a", "b"))


# ── transparent: no routine at all ────────────────────────────────────────


def test_a_transparent_clone_builds_nothing_and_records_no_range():
    """No routine (an inline group) — every build field says "nothing"."""
    clone = _clone()
    bake_product_build(clone, None)
    assert clone.completion == -1
    assert clone.mode == BUILD_TRANSPARENT
    assert clone.ctor is no_construction
    assert clone.matched == ""
    assert clone.n_items == 0
    assert clone.fields == ()
    assert clone.plan == ()
    assert clone.fast is no_fast_construction
    assert clone.defaults is None
    assert clone.needs_ends is False


# ── pass-through: construction is None, a real source ────────────────────


def test_a_pass_through_routine_builds_alt_mode_with_no_construction():
    """A PASS instruction (construction None, source >= 0) is BUILD_ALT."""
    clone = _clone()
    routine = _routine((int(CaptureMode.ONE),), (0,), 0, 3, None)
    bake_product_build(clone, routine)
    assert clone.completion == 7
    assert clone.mode == BUILD_ALT
    assert clone.ctor is no_construction
    assert clone.fields == ()


def test_a_construction_less_routine_with_no_source_builds_seq_mode():
    """construction is None but source < 0 (a collection-begin op) is BUILD_SEQ."""
    clone = _clone()
    routine = _routine((), (), 2, -1, None)
    bake_product_build(clone, routine)
    assert clone.mode == BUILD_SEQ


# ── value_str: construction.matched set ──────────────────────────────────


def test_a_matched_construction_builds_value_str_mode():
    """A rule whose completion fills a field from its own extent."""
    clone = _clone()
    construction = Construction(_Rec, (), frozenset(), matched="a")
    routine = _routine((), (), 0, -1, construction)
    bake_product_build(clone, routine)
    assert clone.mode == BUILD_VALUE_STR
    assert clone.ctor is _Rec
    assert clone.matched == "a"


def test_a_matched_construction_with_no_licence_gets_no_positional_plan():
    """Without a validation-skip licence, the fused build stays keyword-only."""
    clone = _clone()
    construction = Construction(_Rec, (), frozenset(), matched="a")
    routine = _routine((), (), 0, -1, construction)
    bake_product_build(clone, routine)
    assert clone.plan == ()
    assert clone.fast is no_fast_construction
    assert clone.defaults is None


def test_a_licensed_construction_bakes_the_positional_plan():
    """A licence grants the class-ordered positional plan."""
    clone = _clone()
    make, _defaults, order = _Rec.fast_construct()
    licence = (make, {"b": "default-b"}, order)
    construction = Construction(
        _Rec,
        ("a",),
        frozenset(),
        defaults={"b": "default-b"},
        licence=licence,
    )
    routine = _routine((int(CaptureMode.TEXT),), (0,), 1, -1, construction)
    bake_product_build(clone, routine)
    assert clone.fast is make
    assert clone.defaults == {"b": "default-b"}
    assert clone.plan == ((M_TEXT, 0, 1, None), (M_CONST, 0, 0, "default-b"))


def test_a_licensed_matched_field_gets_the_m_value_plan_entry():
    """The field the rule's own extent fills is M_VALUE, not M_CONST."""
    clone = _clone()
    make, _defaults, order = _Rec.fast_construct()
    licence = (make, {}, order)
    construction = Construction(_Rec, ("a",), frozenset(), matched="b", licence=licence)
    routine = _routine((int(CaptureMode.TEXT),), (0,), 1, -1, construction)
    bake_product_build(clone, routine)
    assert clone.plan[1][0] == M_VALUE


# ── keyword capture layout — absence coded on `lo`, not on mode alone ────


def test_a_required_text_capture_codes_as_m_text():
    """A capture not in `optional` is a required M_TEXT, lo=1."""
    clone = _clone()
    construction = Construction(_Rec, ("a",), frozenset(), matched="")
    routine = _routine((int(CaptureMode.TEXT),), (2,), 1, -1, construction)
    bake_product_build(clone, routine)
    assert clone.fields == ((2, M_TEXT, "a", 1),)


def test_an_optional_text_capture_codes_as_m_gtext():
    """The SAME TEXT mode becomes M_GTEXT once the capture may be absent —
    the absence question lives on the flat code, not on a separate mode."""
    clone = _clone()
    construction = Construction(_Rec, ("a",), frozenset({0}), matched="")
    routine = _routine((int(CaptureMode.TEXT),), (2,), 1, -1, construction)
    bake_product_build(clone, routine)
    assert clone.fields == ((2, M_GTEXT, "a", 0),)


def test_a_one_capture_codes_as_m_model_regardless_of_absence():
    """ONE/MANY/EXTENT do not split on absence — only `lo` carries it."""
    clone = _clone()
    construction = Construction(_Rec, ("a",), frozenset({0}), matched="")
    routine = _routine((int(CaptureMode.ONE),), (2,), 1, -1, construction)
    bake_product_build(clone, routine)
    assert clone.fields == ((2, M_MODEL, "a", 0),)


def test_a_skip_mode_capture_refuses_with_words():
    """SKIP fills no model field — a completion cannot build from it."""
    clone = _clone()
    construction = Construction(_Rec, ("a",), frozenset(), matched="")
    routine = _routine((int(CaptureMode.SKIP),), (0,), 1, -1, construction)
    with pytest.raises(UnsupportedConstructError, match="fills no model field"):
        bake_product_build(clone, routine)


# ── provenance and arm width travel unchanged ────────────────────────────


def test_the_baked_completion_and_n_items_are_the_routines_own():
    """The clone's completion/n_items are read straight off the routine —
    one reading, not a second derivation that could disagree."""
    clone = _clone()
    routine = _routine((), (), 5, 0, None)
    bake_product_build(clone, routine)
    assert clone.completion == 7
    assert clone.n_items == 5
