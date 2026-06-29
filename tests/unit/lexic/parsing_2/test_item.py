"""Tests for lexic.parsing_2.item — EarleyItem dotted-arm state record.

The accessors ``is_complete``, ``next_item``, ``next_symbol``, and ``advance``
were inlined at their call sites (spec Q3 resolution). Tests that targeted them
directly are re-expressed with the equivalent inline form:

- ``is_complete``  → ``item[2] >= len(item[1])``
- ``next_item``    → ``item[1][item[2]]`` when not complete, else ``IrNone``
- ``next_symbol``  → ``item[1][item[2]].atom`` when not complete, else ``IrNone``
- ``advance``      → ``(item[0], item[1], item[2] + 1, item[3])``

``EarleyItem`` is a plain-tuple type alias ``tuple[IrRuleRef, IrSequence, int, int]``;
positional fields: [0]=rule_name, [1]=arm, [2]=dot, [3]=origin.
"""

from __future__ import annotations

from lexic.ir.base import IrNone, IrNoneType
from lexic.ir.nodes import IrItem, IrLiteral, IrQuantifier, IrRuleRef, IrSequence
from lexic.parsing_2.item import EarleyItem

# ── Helpers ───────────────────────────────────────────────────────────

_ONE = IrQuantifier(1, 1)


def _arm(*chars: str) -> IrSequence:
    """Build an IrSequence of single-char IrLiteral items."""
    return IrSequence(*(IrItem(IrLiteral(c)) for c in chars))


def _item(arm: IrSequence, dot: int = 0, origin: int = 0) -> EarleyItem:
    return (IrRuleRef("s"), arm, dot, origin)


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
