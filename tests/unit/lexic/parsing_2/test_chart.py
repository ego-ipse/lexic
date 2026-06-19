"""Tests for lexic.parsing_2.chart — Column, Chart, Link, Links.

API changes from the IrSelf rewrite:

- ``Column.add(item) -> bool`` removed.
  Use ``item in column`` for membership, ``column += item`` to insert.
  Tests that tested the bool return value are re-expressed with the new dunder
  idiom; the behavioral intent (dedup) is preserved.

- ``Column.to_scan`` removed (driver re-derives scannable items by filtering the
  closed column). Tests whose *sole* purpose was ``to_scan`` are removed.

- ``Chart.ensure(i)`` removed. Accessing ``chart[i]`` auto-grows. Tests
  re-expressed via indexed access.

- ``chart.links`` is now a ``Links`` object (not a bare ``{}``) keyed on
  ``(EarleyItem, int)`` → ``Link`` record (not a bare 3-tuple). Tests updated
  to construct and inspect ``Link`` instances.

New symbols tested: ``Link`` (fields: predecessor, predecessor_end, child),
``Links`` (``__contains__``, ``__getitem__``, ``__setitem__``).
"""

from __future__ import annotations

from lexic.ir.nodes import IrItem, IrLiteral, IrRuleRef, IrSequence
from lexic.parsing_2.chart import Chart, Column, Link, Links
from lexic.parsing_2.item import EarleyItem


def _arm(*chars: str) -> IrSequence:
    """Build an IrSequence of single-char IrLiteral items."""
    return IrSequence(*(IrItem(IrLiteral(c)) for c in chars))


def _ei(rule: str, arm: IrSequence, dot: int = 0, origin: int = 0) -> EarleyItem:
    return EarleyItem(IrRuleRef(rule), arm, dot, origin)


# ── Column insert / dedup (was Column.add) ───────────────────────────


def test_column_insert_new_item_accepted():
    """Inserting a new item (not yet present) succeeds: item in col is False before, True after."""
    col = Column(0)
    item = _ei("s", _arm("x"))
    assert item not in col
    col += item
    assert item in col


def test_column_insert_duplicate_idempotent():
    """Inserting the same item twice does not grow the column."""
    col = Column(0)
    item = _ei("s", _arm("x"))
    col += item
    col += item
    assert len(col) == 1


def test_column_insert_different_items_both_accepted():
    """Two distinct items are both inserted; col grows to length 2."""
    col = Column(0)
    arm = _arm("x", "y")
    item1 = _ei("a", arm, dot=0)
    item2 = _ei("b", arm, dot=0)
    col += item1
    col += item2
    assert len(col) == 2


def test_column_insert_uses_equality_not_identity():
    """Two equal (but distinct object) items — the second is a duplicate."""
    col = Column(0)
    arm = _arm("z")
    i1 = _ei("s", arm, 0, 0)
    i2 = _ei("s", arm, 0, 0)
    assert i1 is not i2
    col += i1
    assert i2 in col  # equal, so treated as duplicate
    col += i2
    assert len(col) == 1


def test_column_contains_false_before_insert():
    """item not in col before insertion."""
    col = Column(0)
    item = _ei("s", _arm("a"))
    assert item not in col


def test_column_contains_true_after_insert():
    """item in col after insertion."""
    col = Column(0)
    item = _ei("s", _arm("a"))
    col += item
    assert item in col


# ── Column iteration order ────────────────────────────────────────────


def test_column_iteration_preserves_insertion_order():
    """Iterating a column yields items in insertion order."""
    col = Column(0)
    arm = _arm("a", "b", "c")
    items = [_ei("s", arm, d) for d in range(3)]
    for item in items:
        col += item
    assert list(col) == items


def test_column_getitem_by_index():
    """column[i] returns the item at position i."""
    col = Column(0)
    arm = _arm("x")
    item = _ei("s", arm)
    col += item
    assert col[0] is item


# ── Column.index ─────────────────────────────────────────────────────


def test_column_carries_its_index():
    """Column.index matches the value passed at construction."""
    assert Column(0).index == 0
    assert Column(5).index == 5


# ── Chart auto-grow (was Chart.ensure) ───────────────────────────────


def test_chart_indexing_creates_missing_columns():
    """chart[i] auto-grows the chart so column i exists."""
    chart = Chart()
    _ = chart[0]
    assert len(chart) == 1
    _ = chart[3]
    assert len(chart) == 4


def test_chart_indexing_is_idempotent():
    """chart[i] when column i already exists does not add duplicates."""
    chart = Chart()
    _ = chart[2]
    _ = chart[2]
    assert len(chart) == 3


def test_chart_columns_are_indexed_by_position():
    """chart[i].index == i after accessing chart[3]."""
    chart = Chart()
    _ = chart[3]
    for i in range(4):
        assert chart[i].index == i


# ── Link record ───────────────────────────────────────────────────────


def test_link_has_predecessor_field():
    """Link.predecessor holds the predecessor EarleyItem."""
    arm = _arm("x")
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = Link(pred, 0, child)
    assert link.predecessor is pred


def test_link_has_predecessor_end_field():
    """Link.predecessor_end holds the column the predecessor ends at."""
    arm = _arm("x")
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = Link(pred, 5, child)
    assert link.predecessor_end == 5


def test_link_has_child_field():
    """Link.child holds the node consumed to advance the dot."""
    arm = _arm("x")
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = Link(pred, 0, child)
    assert link.child is child


# ── Links table ───────────────────────────────────────────────────────


def test_links_starts_empty():
    """A freshly constructed Links table contains no entries."""
    links = Links()
    arm = _arm("x")
    key = (_ei("s", arm, dot=1), 1)
    assert key not in links


def test_links_setitem_and_getitem():
    """Setting and retrieving a key returns the same Link."""
    links = Links()
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = Link(pred, 0, child)
    links[(item, 1)] = link
    assert links[(item, 1)] is link


def test_links_contains_after_setitem():
    """Key is found in links after assignment."""
    links = Links()
    arm = _arm("y")
    item = _ei("r", arm, dot=1)
    link = Link(item, 0, IrLiteral("y"))
    key = (item, 1)
    links[key] = link
    assert key in links


# ── Chart.links integration ───────────────────────────────────────────


def test_chart_links_starts_empty():
    """chart.links contains no entries at construction."""
    chart = Chart()
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    assert (item, 1) not in chart.links


def test_chart_links_can_be_written_and_read_as_link_record():
    """chart.links accepts (item, end) → Link entries; returns Link record."""
    chart = Chart()
    _ = chart[1]
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = Link(pred, 0, child)
    chart.links[(item, 1)] = link
    retrieved = chart.links[(item, 1)]
    assert retrieved.predecessor is pred
    assert retrieved.predecessor_end == 0
    assert retrieved.child is child
