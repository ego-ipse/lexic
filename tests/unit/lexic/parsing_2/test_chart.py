"""Tests for lexic.parsing_2.chart — Chart, Link, Links.

API changes from the int-kernel rework:

- ``Column`` is COMPLETELY GONE. The per-column Earley sets now live in the
  compiled kernel (:mod:`lexic.parsing_2.kernel`), packed as ints. All
  ``Column``-specific tests (insert/dedup/iteration/getitem/index, Chart
  auto-grow via ``chart[i]``, ``Column.leo``) are DROPPED — that behavior
  now lives on ``Kernel``/``KernelState`` and is tested in ``test_kernel.py``,
  not here.
- ``Chart()`` no longer takes an index and there is no ``chart[i]`` access.
  ``Chart`` is now only ``links`` (a :class:`Links`) + ``leo_links`` (an
  :class:`~lexic.ir.mapping.IrMultiMap`) — a pure decoded-forest carrier
  populated by :meth:`~lexic.parsing_2.kernel.Kernel.to_chart`.

The ``Link`` / ``Links`` tests (constructing tuples, ``Links()`` ``+=``/``in``/
``[]``, multi-family dedup, live-bucket semantics) and ``Chart`` construction
are STILL VALID against current ``chart.py`` and are kept below.
"""

from __future__ import annotations

from lexic.ir.mapping import IrMultiMap
from lexic.ir.nodes import IrItem, IrLiteral, IrRuleRef, IrSequence
from lexic.parsing_2.chart import Chart, Links
from lexic.parsing_2.item import EarleyItem


def _arm(*chars: str) -> IrSequence:
    """Build an IrSequence of single-char IrLiteral items."""
    return IrSequence(*(IrItem(IrLiteral(c)) for c in chars))


def _ei(rule: str, arm: IrSequence, dot: int = 0, origin: int = 0) -> EarleyItem:
    return (IrRuleRef(rule), arm, dot, origin)


# ── Chart construction ─────────────────────────────────────────────────


def test_chart_construction_has_empty_links():
    """A freshly constructed Chart has an empty Links table."""
    chart = Chart()
    assert len(chart.links) == 0


def test_chart_links_is_links_instance():
    """chart.links is a Links instance."""
    chart = Chart()
    assert isinstance(chart.links, Links)


def test_chart_leo_links_is_ir_multi_map():
    """chart.leo_links is an IrMultiMap instance."""
    chart = Chart()
    assert isinstance(chart.leo_links, IrMultiMap)


def test_chart_leo_links_starts_empty():
    """chart.leo_links has no entries at construction."""
    chart = Chart()
    ref = IrRuleRef("s")
    assert len(chart.leo_links[ref]) == 0


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
    """links[missing_key] returns an empty sequence (not an error)."""
    links = Links()
    arm = _arm("z")
    key = (_ei("s", arm, dot=1), 99)
    families = links[key]
    assert len(families) == 0
