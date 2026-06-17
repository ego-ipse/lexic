"""Tests for lexic.parsing_2.chart — Column and Chart Earley sets."""

from __future__ import annotations

from lexic.ir.nodes import IrItem, IrLiteral, IrRuleRef, IrSequence
from lexic.parsing_2.chart import Chart, Column
from lexic.parsing_2.item import EarleyItem


def _arm(*chars: str) -> IrSequence:
    """Build an IrSequence of single-char IrLiteral items."""
    return IrSequence(*(IrItem(IrLiteral(c)) for c in chars))


def _ei(rule: str, arm: IrSequence, dot: int = 0, origin: int = 0) -> EarleyItem:
    return EarleyItem(IrRuleRef(rule), arm, dot, origin)


# ── Column.add ────────────────────────────────────────────────────────


def test_column_add_new_item_returns_true():
    """add() returns True for a freshly inserted item."""
    col = Column(0)
    item = _ei("s", _arm("x"))
    assert col.add(item) is True


def test_column_add_duplicate_returns_false():
    """add() returns False when the same item is inserted again."""
    col = Column(0)
    item = _ei("s", _arm("x"))
    col.add(item)
    assert col.add(item) is False


def test_column_add_different_items_both_accepted():
    """Two distinct items are both accepted; col grows to length 2."""
    col = Column(0)
    arm = _arm("x", "y")
    item1 = _ei("a", arm, dot=0)
    item2 = _ei("b", arm, dot=0)
    assert col.add(item1) is True
    assert col.add(item2) is True
    assert len(col) == 2


def test_column_add_only_equality_matters_not_identity():
    """Two equal (but distinct object) items — the second is a duplicate."""
    col = Column(0)
    arm = _arm("z")
    i1 = _ei("s", arm, 0, 0)
    i2 = _ei("s", arm, 0, 0)
    assert i1 is not i2
    col.add(i1)
    assert col.add(i2) is False


# ── Column iteration order ────────────────────────────────────────────


def test_column_iteration_preserves_insertion_order():
    """Iterating a column yields items in insertion order."""
    col = Column(0)
    arm = _arm("a", "b", "c")
    items = [_ei("s", arm, d) for d in range(3)]
    for item in items:
        col.add(item)
    assert list(col) == items


def test_column_getitem_by_index():
    """column[i] returns the item at position i."""
    col = Column(0)
    arm = _arm("x")
    item = _ei("s", arm)
    col.add(item)
    assert col[0] is item


# ── Column.to_scan ────────────────────────────────────────────────────


def test_column_to_scan_starts_empty():
    """to_scan is empty on a fresh column."""
    col = Column(0)
    assert col.to_scan == []


def test_column_to_scan_is_mutable_list():
    """Items can be appended to to_scan (engine writes terminal items there)."""
    col = Column(0)
    item = _ei("s", _arm("x"))
    col.to_scan.append(item)
    assert len(col.to_scan) == 1
    assert col.to_scan[0] is item


# ── Column.index ─────────────────────────────────────────────────────


def test_column_carries_its_index():
    """Column.index matches the value passed at construction."""
    assert Column(0).index == 0
    assert Column(5).index == 5


# ── Chart.ensure ─────────────────────────────────────────────────────


def test_chart_ensure_creates_missing_columns():
    """ensure(i) grows the chart so column i exists."""
    chart = Chart()
    chart.ensure(0)
    assert len(chart) == 1
    chart.ensure(3)
    assert len(chart) == 4


def test_chart_ensure_is_idempotent():
    """ensure(i) when column i already exists does nothing."""
    chart = Chart()
    chart.ensure(2)
    chart.ensure(2)
    assert len(chart) == 3


def test_chart_columns_are_indexed_by_position():
    """chart[i].index == i after ensure(i)."""
    chart = Chart()
    chart.ensure(3)
    for i in range(4):
        assert chart[i].index == i


# ── Chart.links ───────────────────────────────────────────────────────


def test_chart_links_starts_empty():
    """Chart.links is empty at construction."""
    chart = Chart()
    assert chart.links == {}


def test_chart_links_can_be_written():
    """Chart.links accepts (item, end) → (predecessor, predecessor_end, child) entries."""
    chart = Chart()
    chart.ensure(1)
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    chart.links[(item, 1)] = (pred, 0, child)
    assert chart.links[(item, 1)] == (pred, 0, child)
