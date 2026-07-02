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

from lexic.ir.base import IrNone, IrNoneType
from lexic.ir.mapping import IrMultiMap
from lexic.ir.nodes import IrItem, IrLiteral, IrQuantifier, IrRuleRef, IrSequence
from lexic.parsing_2.chart import Chart, EarleyItem, Links

# ── Helpers ─────────────────────────────────────────────────


def _arm(*chars: str) -> IrSequence:
    """Build an IrSequence of single-char IrLiteral items."""
    return IrSequence(*(IrItem(IrLiteral(c)) for c in chars))


def _ei(rule: str, arm: IrSequence, dot: int = 0, origin: int = 0) -> EarleyItem:
    return (IrRuleRef(rule), arm, dot, origin)


_ONE = IrQuantifier(1, 1)


def _item(arm: IrSequence, dot: int = 0, origin: int = 0) -> EarleyItem:
    return (IrRuleRef("s"), arm, dot, origin)


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


# ── is_complete (inlined as dot >= len(arm)) ──────────────────────────


def test_is_complete_false_when_dot_at_start():
    """Dot at position 0 in a non-empty arm is not complete."""
    arm = _arm("x", "y")
    item = _item(arm, dot=0)
    assert item[2] < len(item[1])


def test_is_complete_false_when_dot_mid_arm():
    """Dot at position 1 in a two-symbol arm is not complete."""
    arm = _arm("x", "y")
    item = _item(arm, dot=1)
    assert item[2] < len(item[1])


def test_is_complete_true_when_dot_past_last_symbol():
    """Dot at len(arm) is complete."""
    arm = _arm("x", "y")
    item = _item(arm, dot=2)
    assert item[2] >= len(item[1])


def test_is_complete_true_for_empty_arm():
    """An empty arm with dot=0 is immediately complete (epsilon production)."""
    arm = IrSequence()
    item = _item(arm, dot=0)
    assert item[2] >= len(item[1])


# ── next_item (inlined as arm[dot] or IrNone) ─────────────────────────


def test_next_item_returns_ir_item_at_dot():
    """The IrItem at the dot position is arm[dot]."""
    arm = _arm("a", "b")
    item = _item(arm, dot=0)
    result = item[1][item[2]] if item[2] < len(item[1]) else IrNone
    assert isinstance(result, IrItem)
    assert result.atom == IrLiteral("a")


def test_next_item_advances_with_dot():
    """arm[dot] at dot=1 returns the second symbol."""
    arm = _arm("a", "b")
    item = _item(arm, dot=1)
    result = item[1][item[2]] if item[2] < len(item[1]) else IrNone
    assert isinstance(result, IrItem)
    assert result.atom == IrLiteral("b")


def test_next_item_returns_irnone_when_complete():
    """When the arm is exhausted arm[dot] is out-of-range; the inline form yields IrNone."""
    arm = _arm("x")
    item = _item(arm, dot=1)
    result = item[1][item[2]] if item[2] < len(item[1]) else IrNone
    assert result is IrNone


def test_next_item_returns_irnone_for_empty_arm():
    """On an empty arm, dot == 0 == len(arm), so the inline form yields IrNone."""
    arm = IrSequence()
    item = _item(arm, dot=0)
    result = item[1][item[2]] if item[2] < len(item[1]) else IrNone
    assert result is IrNone


# ── next_symbol (inlined as arm[dot].atom or IrNone) ─────────────────


def test_next_symbol_returns_atom_at_dot():
    """The atom at the dot is arm[dot].atom."""
    arm = _arm("x")
    item = _item(arm, dot=0)
    sym = item[1][item[2]].atom if item[2] < len(item[1]) else IrNone
    assert isinstance(sym, IrLiteral)
    assert sym == IrLiteral("x")


def test_next_symbol_returns_ruleref_atom():
    """Returns an IrRuleRef when the next atom is a rule reference."""
    arm = IrSequence(IrItem(IrRuleRef("expr")))
    item = _item(arm, dot=0)
    sym = item[1][item[2]].atom if item[2] < len(item[1]) else IrNone
    assert isinstance(sym, IrRuleRef)
    assert sym == IrRuleRef("expr")


def test_next_symbol_returns_irnone_when_complete():
    """Returns IrNone (the absence sentinel) when the arm is done."""
    arm = _arm("x")
    item = _item(arm, dot=1)
    sym = item[1][item[2]].atom if item[2] < len(item[1]) else IrNone
    assert sym is IrNone
    assert isinstance(sym, IrNoneType)


def test_next_symbol_returns_irnone_for_empty_arm():
    """Returns IrNone immediately on an empty arm."""
    arm = IrSequence()
    item = _item(arm, dot=0)
    sym = item[1][item[2]].atom if item[2] < len(item[1]) else IrNone
    assert sym is IrNone


# ── advance (inlined as (..., dot+1, ...)) ────────────────────────────


def test_advance_increments_dot_by_one():
    """Constructing with dot+1 gives a new item with dot incremented."""
    arm = _arm("a", "b", "c")
    item = _item(arm, dot=1)
    advanced = (item[0], item[1], item[2] + 1, item[3])
    assert advanced[2] == 2


def test_advance_preserves_other_fields():
    """The advanced item keeps rule_name, arm, and origin unchanged."""
    arm = _arm("x", "y")
    item: EarleyItem = (IrRuleRef("test"), arm, 1, 3)
    advanced = (item[0], item[1], item[2] + 1, item[3])
    assert advanced[0] == IrRuleRef("test")
    assert advanced[1] is arm
    assert advanced[3] == 3


def test_advance_returns_new_object():
    """The advanced item is a distinct tuple (not the same object)."""
    arm = _arm("x")
    item = _item(arm)
    advanced = (item[0], item[1], item[2] + 1, item[3])
    assert advanced is not item


def test_advance_makes_item_complete():
    """Advancing a one-symbol arm produces a complete item (dot >= len(arm))."""
    arm = _arm("x")
    item = _item(arm, dot=0)
    assert item[2] < len(item[1])
    advanced = (item[0], item[1], item[2] + 1, item[3])
    assert advanced[2] >= len(advanced[1])


# ── equality and hashing ──────────────────────────────────────────────


def test_equal_items_compare_equal():
    """Two items with the same four fields are equal."""
    arm = _arm("a", "b")
    i1: EarleyItem = (IrRuleRef("s"), arm, 0, 0)
    i2: EarleyItem = (IrRuleRef("s"), arm, 0, 0)
    assert i1 == i2


def test_items_differ_by_dot():
    """Items with different dot positions are not equal."""
    arm = _arm("a", "b")
    assert _item(arm, dot=0) != _item(arm, dot=1)


def test_items_differ_by_origin():
    """Items with different origins are not equal."""
    arm = _arm("x")
    assert (IrRuleRef("s"), arm, 0, 0) != (IrRuleRef("s"), arm, 0, 1)


def test_items_differ_by_rule_name():
    """Items with different rule_name IrRuleRefs are not equal."""
    arm = _arm("x")
    assert (IrRuleRef("a"), arm, 0, 0) != (IrRuleRef("b"), arm, 0, 0)


def test_items_are_hashable_and_dedup_in_set():
    """Equal items hash the same and collapse to one element in a set."""
    arm = _arm("x")
    i1: EarleyItem = (IrRuleRef("s"), arm, 0, 0)
    i2: EarleyItem = (IrRuleRef("s"), arm, 0, 0)
    assert len({i1, i2}) == 1


# ── rule_name is IrRuleRef ────────────────────────────────────────────


def test_rule_name_is_irruleref():
    """rule_name must be an IrRuleRef (not a bare str) for type-aware equality."""
    arm = _arm("x")
    item = _item(arm)
    assert isinstance(item[0], IrRuleRef)
