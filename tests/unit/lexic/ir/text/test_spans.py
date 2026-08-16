"""Unit tests for src/lexic/ir/text/spans.py — the address/span vocabulary."""

from __future__ import annotations

from lexic import ir
from lexic.compile import load_ir
from lexic.compile.notation.parse import SYMBOLS
from lexic.ir import (
    IrAddress,
    IrEmission,
    IrExtent,
    IrExtents,
    IrOrigin,
    IrOrigins,
    IrSpan,
    IrStep,
)


def test_the_family_is_exported_from_the_ir_facade() -> None:
    """Every record reaches callers through ``lexic.ir``, not the module path."""
    for name in (
        "IrAddress",
        "IrEmission",
        "IrExtent",
        "IrExtents",
        "IrOrigin",
        "IrOrigins",
        "IrSpan",
        "IrStep",
    ):
        assert name in ir.__all__, name
        assert hasattr(ir, name), name


# ── IrStep / IrAddress ──────────────────────────────────────────────────


def test_a_step_carries_the_field_name_and_the_slot() -> None:
    """Both halves are readable by name and by position — a record IS its tuple."""
    step = IrStep("ws", 2)
    assert (step.field, step.slot) == ("ws", 2)
    assert step[0] == "ws" and step[1] == 2


def test_a_step_without_a_name_still_has_an_index() -> None:
    """A structural literal has no field name; its slot still identifies it."""
    assert IrStep("", 3).slot == 3


def test_the_empty_address_is_the_root() -> None:
    """A root occurrence has no steps."""
    assert len(IrAddress()) == 0


def test_child_extends_top_down_and_never_mutates() -> None:
    """``child`` returns a NEW address — the parent is untouched (B1)."""
    root = IrAddress()
    first = root.child("value", 1)
    second = first.child("", 0)
    assert len(root) == 0
    assert list(first) == [IrStep("value", 1)]
    assert list(second) == [IrStep("value", 1), IrStep("", 0)]


def test_two_equal_named_steps_differ_by_index() -> None:
    """The index is what tells two occurrences of one field name apart."""
    a = IrAddress().child("ws", 0)
    b = IrAddress().child("ws", 2)
    assert a != b


def test_an_address_is_its_steps_tuple() -> None:
    """The node IS the tuple: iterate and index it, no accessor in between.

    ``IrSeq``'s element bound is a STATIC guarantee (pyright rejects a
    non-``IrStep``); nothing checks it at runtime, here or on ``IrSequence``.
    """
    address = IrAddress(IrStep("a", 0), IrStep("b", 1))
    assert address[1] == IrStep("b", 1)
    assert [step.field for step in address] == ["a", "b"]


# ── IrSpan ──────────────────────────────────────────────────────────────


def test_a_span_slices_the_text_it_was_measured_against() -> None:
    """``of`` is the whole point: a span selects its own stretch back."""
    assert IrSpan(3, 7).of("0123456789") == "3456"


def test_an_empty_span_is_a_fact_not_an_absence() -> None:
    """``start == end`` is an occurrence that spelled nothing."""
    assert IrSpan(4, 4).of("abcdef") == ""


def test_a_span_is_half_open_in_code_units() -> None:
    """``end`` is one past the last covered unit, so width is ``end - start``."""
    span = IrSpan(0, 2)
    assert span.of("abc") == "ab"
    assert span.end - span.start == 2


# ── the correspondence shapes ───────────────────────────────────────────


def test_an_extent_pairs_an_address_with_a_span() -> None:
    """The emit-side correspondence, readable in both directions."""
    extent = IrExtent(IrAddress().child("ws", 0), IrSpan(0, 3))
    assert extent.address == IrAddress().child("ws", 0)
    assert extent.span.of("   x") == "   "


def test_an_origin_pairs_two_addresses() -> None:
    """The transform-side correspondence uses the same leaves as the extent."""
    origin = IrOrigin(IrAddress().child("out", 0), IrAddress().child("src", 1))
    assert origin.address != origin.source


def test_an_emission_carries_the_text_beside_its_extents() -> None:
    """The halves travel together — spans mean nothing against another text."""
    extents = IrExtents(IrExtent(IrAddress(), IrSpan(0, 2)))
    emission = IrEmission("ab", extents)
    assert emission.text == "ab"
    assert emission.extents[0].span.of(emission.text) == "ab"


# ── spine citizenship ───────────────────────────────────────────────────


def test_every_record_round_trips_through_the_notation() -> None:
    """repr-is-codegen, pinned the repo's way: ``load_ir(repr(x)) == x``.

    Not ``eval`` — the notation's symbol whitelist IS the no-exec boundary,
    and passing through it also proves the family is spellable vocabulary
    rather than merely well-repr'd.
    """
    for value in (
        IrStep("ws", 1),
        IrAddress().child("value", 0),
        IrSpan(1, 4),
        IrExtent(IrAddress().child("value", 0), IrSpan(1, 4)),
        IrExtents(IrExtent(IrAddress(), IrSpan(0, 0))),
        IrEmission("x", IrExtents()),
        IrOrigin(IrAddress(), IrAddress().child("a", 0)),
        IrOrigins(IrOrigin(IrAddress(), IrAddress())),
    ):
        assert load_ir(repr(value)) == value, repr(value)


def test_the_family_is_in_the_notation_vocabulary() -> None:
    """A record outside the whitelist could not be spelled back at all."""
    for cls in (IrStep, IrAddress, IrSpan, IrExtent, IrExtents, IrOrigin):
        assert SYMBOLS.get(cls.__name__) is cls, cls.__name__


def test_scalar_payload_records_declare_no_children() -> None:
    """``IrStep``/``IrSpan`` are scalar payload — the walk does not descend."""
    assert not IrStep("a", 0).children()
    assert not IrSpan(0, 1).children()


def test_the_pair_records_expose_their_leaves_to_the_walk() -> None:
    """An extent's address and span ARE its children — the family is walkable."""
    extent = IrExtent(IrAddress().child("a", 0), IrSpan(0, 1))
    assert extent.children() == (extent.address, extent.span)


def test_records_are_hashable_and_value_equal() -> None:
    """Addresses key a dict — which is what a consumer indexing by them needs."""
    a = IrAddress().child("value", 0)
    b = IrAddress().child("value", 0)
    assert {a: 1}[b] == 1


def test_the_containers_are_their_element_tuples() -> None:
    """``IrExtents``/``IrOrigins`` name a sequence; they ARE it."""
    extent = IrExtent(IrAddress(), IrSpan(0, 1))
    origin = IrOrigin(IrAddress(), IrAddress())
    assert list(IrExtents(extent, extent)) == [extent, extent]
    assert IrOrigins(origin)[0] is origin
    assert len(IrExtents()) == 0
