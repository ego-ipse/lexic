"""IR AST node dataclasses — frozen, hashable, immutable tuples."""

from __future__ import annotations

import pytest

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)

# ── Quantifier ───────────────────────────────────────────────────────


def test_quantifier_default_is_one_one():
    """Test that the default quantifier has min=1 and max=1."""
    q = Quantifier()
    assert q.min == 1 and q.max == 1


def test_quantifier_unbounded_max_is_none():
    """Test that the unbounded quantifier has max=None."""
    q = Quantifier(min=1, max=None)
    assert q.max is None


def test_quantifier_is_frozen():
    """Frozen dataclass rejects attribute mutation."""
    q = Quantifier(0, 1)
    with pytest.raises(AttributeError):
        setattr(q, "min", 5)


def test_quantifier_is_hashable():
    """Equal quantifiers are deduplicated in a set."""
    assert len({Quantifier(0, 1), Quantifier(0, 1)}) == 1


# ── Leaves ───────────────────────────────────────────────────────────


def test_ir_literal_holds_canonical_value():
    """Test that the IR literal holds a canonical value."""
    lit = IrLiteral(value="hello")
    assert lit.value == "hello"


def test_ir_literal_canonical_python_newline():
    """Test that the IR literal holds a canonical Python newline."""
    lit = IrLiteral(value="a\nb")
    assert lit.value == "a\nb"


def test_ir_literal_is_frozen_and_hashable():
    """Frozen dataclass is hashable and deduplicates in sets."""
    assert len({IrLiteral("a"), IrLiteral("a")}) == 1


def test_ir_charclass_default_not_negated():
    """Test that the IR character class is not negated by default."""
    cc = IrCharClass(pattern="a-z")
    assert cc.pattern == "a-z"
    assert cc.negated is False


def test_ir_charclass_negated_flag():
    """Test that the IR character class holds the correct negation flag."""
    cc = IrCharClass(pattern="\\n", negated=True)
    assert cc.negated is True


def test_ir_ruleref_holds_name():
    """Test that the IR rule reference holds the correct name."""
    r = IrRuleRef(name="expr")
    assert r.name == "expr"


# ── IrItem ───────────────────────────────────────────────────────────


def test_ir_item_default_quantifier():
    """Test that the IR item has the correct default quantifier."""
    it = IrItem(atom=IrLiteral("x"))
    assert it.quantifier == Quantifier()


def test_ir_item_with_explicit_quantifier():
    """Test that the IR item can have an explicit quantifier."""
    it = IrItem(atom=IrCharClass("a-z"), quantifier=Quantifier(0, None))
    assert it.quantifier.min == 0
    assert it.quantifier.max is None


def test_ir_item_atom_can_be_group():
    """Test that the IR item can have a group as its atom."""
    grp = IrGroup(IrAlternation((IrSequence((IrItem(IrLiteral("a")),)),)))
    it = IrItem(atom=grp, quantifier=Quantifier(1, None))
    assert isinstance(it.atom, IrGroup)


# ── Structure ────────────────────────────────────────────────────────


def test_ir_sequence_items_are_tuple():
    """Test that the IR sequence holds its items in a tuple."""
    seq = IrSequence((IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))))
    assert isinstance(seq.items, tuple)
    assert len(seq.items) == 2


def test_ir_alternation_arms_are_tuple():
    """Test that the IR alternation holds its arms in a tuple."""
    alt = IrAlternation((IrSequence((IrItem(IrLiteral("a")),)),))
    assert isinstance(alt.arms, tuple)


def test_ir_group_wraps_alternation():
    """An IR group should wrap an IrAlternation body."""
    alt = IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))
    grp = IrGroup(body=alt)
    assert grp.body is alt


def test_ir_rule_has_alternation_body():
    """An IR rule should have a body that is an IrAlternation, even if single-arm."""
    body = IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))
    rule = IrRule(name="r", body=body)
    assert rule.name == "r"
    assert rule.body is body


def test_ir_ast_holds_rules_and_start():
    """An IR AST should hold a tuple of rules and the name of the start rule."""
    body = IrAlternation((IrSequence(()),))
    rule = IrRule(name="root", body=body)
    ast = IrAst(rules=(rule,), start="root")
    assert ast.start == "root"
    assert ast.rules == (rule,)


def test_ir_ast_is_frozen():
    """Frozen dataclass rejects attribute mutation on IrAst."""
    ast = IrAst(rules=(), start="root")
    with pytest.raises(AttributeError):
        setattr(ast, "start", "other")


# ── Equality ─────────────────────────────────────────────────────────


def test_structurally_equal_asts_compare_equal():
    """Two IR ASTs with the same structure and values should compare equal."""
    a = IrAst(
        rules=(IrRule("r", IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))),),
        start="r",
    )
    b = IrAst(
        rules=(IrRule("r", IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))),),
        start="r",
    )
    assert a == b
