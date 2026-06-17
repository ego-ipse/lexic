"""Tests for lexic.parsing_2.item — EarleyItem dotted-arm state record."""

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
    return EarleyItem(IrRuleRef("s"), arm, dot, origin)


# ── is_complete ───────────────────────────────────────────────────────


def test_is_complete_false_when_dot_at_start():
    """Dot at position 0 in a non-empty arm is not complete."""
    arm = _arm("x", "y")
    assert not _item(arm, dot=0).is_complete


def test_is_complete_false_when_dot_mid_arm():
    """Dot at position 1 in a two-symbol arm is not complete."""
    arm = _arm("x", "y")
    assert not _item(arm, dot=1).is_complete


def test_is_complete_true_when_dot_past_last_symbol():
    """Dot at len(arm) is complete."""
    arm = _arm("x", "y")
    assert _item(arm, dot=2).is_complete


def test_is_complete_true_for_empty_arm():
    """An empty arm with dot=0 is immediately complete (epsilon production)."""
    arm = IrSequence()
    assert _item(arm, dot=0).is_complete


# ── next_item ─────────────────────────────────────────────────────────


def test_next_item_returns_ir_item_at_dot():
    """next_item() returns the IrItem at the dot position."""
    arm = _arm("a", "b")
    result = _item(arm, dot=0).next_item()
    assert isinstance(result, IrItem)
    assert result.atom == IrLiteral("a")


def test_next_item_advances_with_dot():
    """next_item() at dot=1 returns the second symbol."""
    arm = _arm("a", "b")
    result = _item(arm, dot=1).next_item()
    assert isinstance(result, IrItem)
    assert result.atom == IrLiteral("b")


def test_next_item_returns_irnone_when_complete():
    """next_item() returns IrNone when the arm is exhausted."""
    arm = _arm("x")
    result = _item(arm, dot=1).next_item()
    assert result is IrNone


def test_next_item_returns_irnone_for_empty_arm():
    """next_item() on an empty arm immediately returns IrNone."""
    arm = IrSequence()
    result = _item(arm, dot=0).next_item()
    assert result is IrNone


# ── next_symbol ───────────────────────────────────────────────────────


def test_next_symbol_returns_atom_at_dot():
    """next_symbol() returns the atom (not the IrItem) at the dot."""
    arm = _arm("x")
    sym = _item(arm, dot=0).next_symbol()
    assert isinstance(sym, IrLiteral)
    assert sym == IrLiteral("x")


def test_next_symbol_returns_ruleref_atom():
    """next_symbol() returns an IrRuleRef when the next atom is a rule reference."""
    arm = IrSequence(IrItem(IrRuleRef("expr")))
    sym = _item(arm, dot=0).next_symbol()
    assert isinstance(sym, IrRuleRef)
    assert sym == IrRuleRef("expr")


def test_next_symbol_returns_irnone_when_complete():
    """next_symbol() returns IrNone (the absence sentinel) when the arm is done."""
    arm = _arm("x")
    sym = _item(arm, dot=1).next_symbol()
    assert sym is IrNone
    assert isinstance(sym, IrNoneType)


def test_next_symbol_returns_irnone_for_empty_arm():
    """next_symbol() on an empty arm returns IrNone immediately."""
    arm = IrSequence()
    sym = _item(arm, dot=0).next_symbol()
    assert sym is IrNone


# ── advance ───────────────────────────────────────────────────────────


def test_advance_increments_dot_by_one():
    """advance() returns a new item with dot + 1."""
    arm = _arm("a", "b", "c")
    item = _item(arm, dot=1)
    advanced = item.advance()
    assert advanced.dot == 2


def test_advance_preserves_other_fields():
    """advance() keeps rule_name, arm, and origin unchanged."""
    arm = _arm("x", "y")
    item = EarleyItem(IrRuleRef("test"), arm, 1, 3)
    advanced = item.advance()
    assert advanced.rule_name == IrRuleRef("test")
    assert advanced.arm is arm
    assert advanced.origin == 3


def test_advance_returns_new_object():
    """advance() returns a distinct EarleyItem (not the same object)."""
    arm = _arm("x")
    item = _item(arm)
    advanced = item.advance()
    assert advanced is not item


def test_advance_makes_item_complete():
    """advance() on a one-symbol arm produces a complete item."""
    arm = _arm("x")
    item = _item(arm, dot=0)
    assert not item.is_complete
    assert item.advance().is_complete


# ── equality and hashing ──────────────────────────────────────────────


def test_equal_items_compare_equal():
    """Two items with the same four fields are equal."""
    arm = _arm("a", "b")
    i1 = EarleyItem(IrRuleRef("s"), arm, 0, 0)
    i2 = EarleyItem(IrRuleRef("s"), arm, 0, 0)
    assert i1 == i2


def test_items_differ_by_dot():
    """Items with different dot positions are not equal."""
    arm = _arm("a", "b")
    assert _item(arm, dot=0) != _item(arm, dot=1)


def test_items_differ_by_origin():
    """Items with different origins are not equal."""
    arm = _arm("x")
    assert EarleyItem(IrRuleRef("s"), arm, 0, 0) != EarleyItem(
        IrRuleRef("s"), arm, 0, 1
    )


def test_items_differ_by_rule_name():
    """Items with different rule_name IrRuleRefs are not equal."""
    arm = _arm("x")
    assert EarleyItem(IrRuleRef("a"), arm, 0, 0) != EarleyItem(
        IrRuleRef("b"), arm, 0, 0
    )


def test_items_are_hashable_and_dedup_in_set():
    """Equal items hash the same and collapse to one element in a set."""
    arm = _arm("x")
    i1 = EarleyItem(IrRuleRef("s"), arm, 0, 0)
    i2 = EarleyItem(IrRuleRef("s"), arm, 0, 0)
    assert len({i1, i2}) == 1


# ── _child_attrs ──────────────────────────────────────────────────────


def test_child_attrs_is_empty_tuple():
    """EarleyItem has no dispatched children — it is engine state, not grammar."""
    item = EarleyItem(IrRuleRef("r"), IrSequence(), 0, 0)
    assert not item.children()


def test_children_returns_empty_tuple():
    """children() returns () — the item has no IR children to walk."""
    arm = _arm("x")
    assert not _item(arm).children()


# ── rule_name is IrRuleRef ────────────────────────────────────────────


def test_rule_name_is_irruleref():
    """rule_name must be an IrRuleRef (not a bare str) for type-aware equality."""
    arm = _arm("x")
    item = _item(arm)
    assert isinstance(item.rule_name, IrRuleRef)
