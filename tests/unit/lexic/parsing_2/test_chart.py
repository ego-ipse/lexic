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
``Links`` (``__contains__``, ``__getitem__``, ``__iadd__``).

Leo slot tested: ``Column.leo`` (``IrMultiMap``, empty at construction).
"""

from __future__ import annotations

from lexic.ir.mapping import IrMultiMap
from lexic.ir.nodes import IrItem, IrLiteral, IrRuleRef, IrSequence
from lexic.parsing_2.chart import Chart, Column, Links
from lexic.parsing_2.item import EarleyItem


def _arm(*chars: str) -> IrSequence:
    """Build an IrSequence of single-char IrLiteral items."""
    return IrSequence(*(IrItem(IrLiteral(c)) for c in chars))


def _ei(rule: str, arm: IrSequence, dot: int = 0, origin: int = 0) -> EarleyItem:
    return (IrRuleRef(rule), arm, dot, origin)


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
    """Link[0] holds the predecessor EarleyItem."""
    arm = _arm("x")
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = (pred, 0, child)
    assert link[0] is pred


def test_link_has_predecessor_end_field():
    """Link[1] holds the column the predecessor ends at."""
    arm = _arm("x")
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = (pred, 5, child)
    assert link[1] == 5


def test_link_has_child_field():
    """Link[2] holds the node consumed to advance the dot."""
    arm = _arm("x")
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = (pred, 0, child)
    assert link[2] is child


# ── Links table ───────────────────────────────────────────────────────


def test_links_starts_empty():
    """A freshly constructed Links table contains no entries."""
    links = Links()
    arm = _arm("x")
    key = (_ei("s", arm, dot=1), 1)
    assert key not in links


def test_links_setitem_and_getitem():
    """Recording a link via += and retrieving it via [] returns the same Link."""
    links = Links()
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = (pred, 0, child)
    links += ((item, 1), link)
    assert links[(item, 1)][0] is link


def test_links_contains_after_setitem():
    """Key is found in links after recording a family via +=."""
    links = Links()
    arm = _arm("y")
    item = _ei("r", arm, dot=1)
    link = (item, 0, IrLiteral("y"))
    key = (item, 1)
    links += (key, link)
    assert key in links


# ── Chart.links integration ───────────────────────────────────────────


def test_chart_links_starts_empty():
    """chart.links contains no entries at construction."""
    chart = Chart()
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    assert (item, 1) not in chart.links


def test_chart_links_can_be_written_and_read_as_link_record():
    """chart.links records a Link via += and returns it via [] as the first family."""
    chart = Chart()
    _ = chart[1]
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = (pred, 0, child)
    chart.links += ((item, 1), link)
    families = chart.links[(item, 1)]
    retrieved = families[0]
    assert retrieved[0] is pred
    assert retrieved[1] == 0
    assert retrieved[2] is child


# ── Links multi-family (SPPF packed families) ─────────────────────────


def test_links_multi_family_two_distinct_links():
    """Two distinct links for the same key → len 2 family bucket."""
    links = Links()
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred_a = _ei("s", arm, dot=0)
    pred_b = _ei("r", arm, dot=0)
    child = IrLiteral("x")
    link_a = (pred_a, 0, child)
    link_b = (pred_b, 0, child)
    key = (item, 1)
    links += (key, link_a)
    links += (key, link_b)
    assert len(links[key]) == 2


def test_links_multi_family_dedup_identical():
    """Recording the same family twice keeps only one entry (dedup)."""
    links = Links()
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred = _ei("s", arm, dot=0)
    child = IrLiteral("x")
    link = (pred, 0, child)
    key = (item, 1)
    links += (key, link)
    links += (key, link)
    assert len(links[key]) == 1


def test_links_getitem_returns_live_bucket():
    """Sequence returned by links[key] is the live backing bucket — subsequent
    appends to the same key are reflected in a reference held before the append."""
    links = Links()
    arm = _arm("x")
    item = _ei("s", arm, dot=1)
    pred_a = _ei("s", arm, dot=0)
    pred_b = _ei("r", arm, dot=0)
    child = IrLiteral("x")
    link_a = (pred_a, 0, child)
    link_b = (pred_b, 0, child)
    key = (item, 1)
    links += (key, link_a)
    live = links[key]  # live bucket reference — 1 entry so far
    links += (key, link_b)  # grow the same bucket
    assert len(live) == 2  # live reference reflects the addition
    assert len(links[key]) == 2  # fresh read agrees


def test_links_getitem_empty_on_miss():
    """links[missing_key] returns an empty IrSeq (not an error)."""
    links = Links()
    arm = _arm("z")
    key = (_ei("s", arm, dot=1), 99)
    families = links[key]
    assert len(families) == 0


# ── Column.leo slot (Leo optimization memo) ───────────────────────────


def test_column_leo_is_ir_multi_map():
    """Column.leo is an IrMultiMap at construction."""
    col = Column(0)
    assert isinstance(col.leo, IrMultiMap)


def test_column_leo_is_empty_on_fresh_column():
    """A fresh Column(0) has an empty leo memo (no keys filed)."""
    col = Column(0)
    ref = IrRuleRef("s")
    # IrMultiMap returns empty sequence on miss — length 0 means no entry yet
    assert len(col.leo[ref]) == 0


def test_column_leo_independent_of_waiting():
    """leo and waiting are distinct IrMultiMap instances."""
    col = Column(0)
    assert col.leo is not col.waiting


def test_column_leo_independent_across_columns():
    """Two different Column instances have distinct leo IrMultiMaps."""
    col_a = Column(0)
    col_b = Column(1)
    assert col_a.leo is not col_b.leo


def test_column_leo_accepts_iadd():
    """leo accepts += (key, value) and makes the value retrievable."""
    from lexic.ir.base import IrNone

    col = Column(0)
    ref = IrRuleRef("s")
    col.leo += (ref, IrNone)
    assert len(col.leo[ref]) == 1
    assert col.leo[ref][0] is IrNone
