"""Tests for lexic.model_emission — stack records and extent reservation.

The end-to-end addressed walk this feeds (``GrammarModel.emit_addressed``)
is exercised over real parsed models in
``tests/integration/lexic/roundtrip/test_addressed_emission.py``; this file
targets ``open_emission``'s own stack-building shape directly.
"""

from __future__ import annotations

from typing import cast

from lexic.ir import IrAddress, IrExtent, IrSpan
from lexic.model_emission import EmissionClose, EmissionPart, open_emission


def _parts(items: list[object]) -> list[EmissionPart]:
    """The :class:`EmissionPart` entries of an ``open_emission`` result."""
    return [
        cast(EmissionPart, item) for item in items if isinstance(item, EmissionPart)
    ]


def test_open_emission_reserves_one_extent_slot_at_the_current_offset():
    """The reserved extent starts and ends at the given offset (a placeholder)."""
    work = EmissionPart("root", IrAddress())
    extents: list[IrExtent] = []
    open_emission(work, [("a", "x")], extents, at=5)
    assert len(extents) == 1
    assert extents[0] == IrExtent(work.address, IrSpan(5, 5))


def test_open_emission_returns_the_close_beneath_its_children_for_a_lifo_stack():
    """Callers pop a list stack LIFO, so the close (processed LAST) must sit
    at the front of the returned list, with children after it in REVERSE
    parts order — so popping restores original field order."""
    work = EmissionPart("root", IrAddress())
    extents: list[IrExtent] = []
    items = open_emission(work, [("a", "x"), ("b", "y")], extents, at=0)
    assert isinstance(items[0], EmissionClose)
    assert [p.part for p in _parts(items[1:])] == ["y", "x"]


def test_open_emission_addresses_each_child_by_field_and_positional_slot():
    """Each child's address is the parent's address extended by field name and slot."""
    work = EmissionPart("root", IrAddress())
    extents: list[IrExtent] = []
    items = open_emission(work, [("a", "x"), ("b", "y")], extents, at=0)
    parts = _parts(items[1:])
    a_part = next(p for p in parts if p.part == "x")
    b_part = next(p for p in parts if p.part == "y")
    assert a_part.address == work.address.child("a", 0)
    assert b_part.address == work.address.child("b", 1)


def test_open_emission_close_carries_the_reserved_slot_address_and_start():
    """The close record names the exact slot it reserved, and the open offset."""
    work = EmissionPart("root", IrAddress())
    extents: list[IrExtent] = []
    extents.append(IrExtent(IrAddress(), IrSpan(0, 0)))  # occupy slot 0
    items = open_emission(work, [], extents, at=3)
    close = items[0]
    assert isinstance(close, EmissionClose)
    assert close.slot == 1
    assert close.address == work.address
    assert close.start == 3


def test_open_emission_with_no_parts_yields_only_the_close():
    """A childless container's stack contribution is the close alone."""
    work = EmissionPart("root", IrAddress())
    extents: list[IrExtent] = []
    items = open_emission(work, [], extents, at=0)
    assert len(items) == 1
    assert isinstance(items[0], EmissionClose)
