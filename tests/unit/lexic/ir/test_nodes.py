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
    IrNode,
    IrNone,
    IrNot,
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


def test_ir_charclass_holds_pattern():
    """Test that the IR character class holds the pattern."""
    cc = IrCharClass(pattern="a-z")
    assert cc.pattern == "a-z"


def test_ir_not_wraps_charclass():
    """Test that IrNot wraps a charclass atom."""
    cc = IrCharClass(pattern="\\n")
    node = IrNot[IrCharClass](body=cc)
    assert node.body is cc
    assert node.body.pattern == "\\n"


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


# ── IrNode structural protocol ───────────────────────────────────────


def test_irnode_is_abc_base_class():
    """Every concrete IR node inherits from IrNode."""
    for cls in (
        IrAst,
        IrRule,
        IrAlternation,
        IrSequence,
        IrItem,
        IrGroup,
        IrLiteral,
        IrCharClass,
        IrRuleRef,
        Quantifier,
    ):
        assert issubclass(cls, IrNode), f"{cls.__name__} must inherit IrNode"


def test_irnode_default_children_is_empty_tuple():
    """Leaves inherit empty-tuple default."""
    assert not IrLiteral("x").children()
    assert not IrCharClass("a-z").children()
    assert not IrRuleRef("foo").children()
    assert not Quantifier().children()


def test_irnode_default_rebuild_is_identity():
    """Leaves inherit identity rebuild."""
    leaf = IrLiteral("x")
    assert leaf.rebuild(()) is leaf


def test_iritem_children_returns_atom_and_quantifier():
    """An IrItem's children are its atom and quantifier."""
    item = IrItem(IrLiteral("x"), Quantifier(0, None))
    assert item.children() == (item.atom, item.quantifier)


def test_iritem_rebuild_replaces_atom_and_quantifier():
    """Rebuilding an IrItem replaces both atom and quantifier from new_children."""
    item = IrItem(IrLiteral("x"), Quantifier(0, None))
    new = item.rebuild((IrLiteral("y"), Quantifier(1, 3)))
    assert new == IrItem(IrLiteral("y"), Quantifier(1, 3))


def test_irsequence_children_returns_items():
    """An IrSequence's children are its items."""
    a, b = IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))
    seq = IrSequence((a, b))
    assert seq.children() == (a, b)


def test_irsequence_rebuild_replaces_items():
    """Rebuilding an IrSequence replaces its items."""
    a, b = IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))
    seq = IrSequence((a,))
    assert seq.rebuild((a, b)) == IrSequence((a, b))


def test_iralternation_children_returns_arms():
    """An IrAlternation's children are its arms."""
    s = IrSequence(())
    alt = IrAlternation((s,))
    assert alt.children() == (s,)


def test_iralternation_rebuild_replaces_arms():
    """Rebuilding an IrAlternation replaces its arms."""
    s1, s2 = IrSequence(()), IrSequence(())
    assert IrAlternation((s1,)).rebuild((s1, s2)) == IrAlternation((s1, s2))


def test_irgroup_children_returns_body():
    """An IrGroup's children are its body."""
    body = IrAlternation(())
    grp = IrGroup(body)
    assert grp.children() == (body,)


def test_irgroup_rebuild_replaces_body():
    """Rebuilding an IrGroup replaces its body."""
    b1, b2 = IrAlternation(()), IrAlternation((IrSequence(()),))
    assert IrGroup(b1).rebuild((b2,)) == IrGroup(b2)


def test_irrule_children_returns_body():
    """An IrRule's children are its body."""
    body = IrAlternation(())
    rule = IrRule("r", body)
    assert rule.children() == (body,)


def test_irrule_rebuild_replaces_body_preserves_name():
    """Rebuilding an IrRule replaces its body but preserves the name."""
    b1, b2 = IrAlternation(()), IrAlternation((IrSequence(()),))
    assert IrRule("r", b1).rebuild((b2,)) == IrRule("r", b2)


def test_irast_children_returns_rules():
    """An IrAst's children are its rules."""
    r = IrRule("x", IrAlternation(()))
    ast = IrAst((r,), "x")
    assert ast.children() == (r,)


def test_irast_rebuild_replaces_rules_preserves_start():
    """Rebuilding an IrAst replaces its rules but preserves the start name."""
    r1 = IrRule("a", IrAlternation(()))
    r2 = IrRule("b", IrAlternation(()))
    assert IrAst((r1,), "a").rebuild((r1, r2)) == IrAst((r1, r2), "a")


def test_str_irliteral():
    """An IrLiteral's string is its value."""
    assert str(IrLiteral("a")) == "LITERAL('a')"


def test_str_ircharclass():
    """An IrCharClass's string is its pattern."""
    assert str(IrCharClass("a-z")) == "CHARCLASS('a-z')"


def test_str_irnot_wrapping_charclass():
    """IrNot wrapping a charclass includes the negation in its str."""
    assert str(IrNot(IrCharClass("0-9"))) == "NOT(CHARCLASS('0-9'))"


def test_str_irruleref():
    """An IrRuleRef's string is its name."""
    assert str(IrRuleRef("expr")) == "REF('expr')"


def test_str_quantifier():
    """A Quantifier's string is its bounds."""
    assert str(Quantifier(1, 1)) == "Q[1]"
    assert str(Quantifier(0, 1)) == "Q[0..1]"
    assert str(Quantifier(0, None)) == "Q[0..*]"
    assert str(Quantifier(2, 5)) == "Q[2..5]"


def test_str_irsequence():
    """An IrSequence's string is its items."""
    seq = IrSequence((IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))))
    assert str(seq) == "SEQ(ITEM(LITERAL('a'), Q[1]), ITEM(LITERAL('b'), Q[1]))"


def test_str_irrule_includes_name():
    """An IrRule's string is its name and body."""
    rule = IrRule("r", IrAlternation((IrSequence(()),)))
    assert str(rule) == "RULE('r', ALT(SEQ()))"


def test_str_irast_includes_start():
    """An IrAst's string is its start and rules."""
    ast = IrAst(rules=(IrRule("r", IrAlternation(())),), start="r")
    assert str(ast) == "AST(start='r', RULE('r', ALT()))"


# __repr__ — indented debug walk
def test_repr_irliteral_is_dataclass_default():
    """An IrLiteral's repr is the default dataclass repr."""
    assert repr(IrLiteral("a")) == "IrLiteral(value='a')"


def test_repr_irsequence_is_indented_multiline():
    """An IrSequence's repr is an indented multiline walk of its items."""
    seq = IrSequence((IrItem(IrLiteral("a")),))
    assert repr(seq) == (
        "IrSequence(\n"
        "  IrItem(\n"
        "    IrLiteral(value='a'),\n"
        "    Quantifier(min=1, max=1)\n"
        "  )\n"
        ")"
    )


def test_repr_irrule_shows_non_child_fields_too():
    """name appears alongside the recursed body."""
    rule = IrRule("r", IrAlternation(()))
    assert repr(rule) == ("IrRule(\n  name='r',\n  IrAlternation()\n)")


def test_str_iralternation():
    """An IrAlternation's string is its arms."""
    alt = IrAlternation((IrSequence(()),))
    assert str(alt) == "ALT(SEQ())"


def test_str_irgroup():
    """An IrGroup's string is its body."""
    grp = IrGroup(IrAlternation(()))
    assert str(grp) == "GROUP(ALT())"


def test_str_iritem():
    """An IrItem's string is its atom and quantifier."""
    assert str(IrItem(IrLiteral("a"))) == "ITEM(LITERAL('a'), Q[1])"


# __repr__ — additional coverage


def test_repr_empty_structural_node():
    """An empty structural node renders as ClassName() without a newline."""
    assert repr(IrSequence(())) == "IrSequence()"
    assert repr(IrAlternation(())) == "IrAlternation()"


def test_repr_irgroup_no_extras():
    """IrGroup (IrComposite with no extras) indents its only child."""
    grp = IrGroup(IrAlternation(()))
    assert repr(grp) == "IrGroup(\n  IrAlternation()\n)"


def test_repr_irast_with_extras_and_children():
    """IrAst renders start= extra then indented rule children."""
    ast = IrAst(rules=(IrRule("r", IrAlternation(())),), start="r")
    assert repr(ast) == (
        "IrAst(\n  start='r',\n  IrRule(\n    name='r',\n    IrAlternation()\n  )\n)"
    )


def test_irliteral_eval_returns_literal_value():
    """IrLiteral overrides ``eval`` to surface ``self.value`` as a str.

    ``__call__`` remains identity (returns self) via :class:`IrSelf`;
    ``eval`` is the value-producing protocol.
    """
    lit = IrLiteral("hello")
    result: str = lit.eval(IrNone, IrNone, ())
    assert result == "hello"


def test_ircharclass_call_inherits_identity_default():
    """IrCharClass(IrLeaf) inherits the default __call__ — returns self.
    Statically typed as IrNode; runtime identity to the concrete instance."""
    cc = IrCharClass("a-z")
    result = cc(IrNone, IrNone, ())  # statically IrNode; runtime IrCharClass
    assert result is cc


def test_irruleref_call_inherits_identity_default():
    """IrRuleRef(IrLeaf) inherits the default __call__ — returns self."""
    ref = IrRuleRef("foo")
    assert ref(IrNone, IrNone, ()) is ref


def test_irast_call_inherits_rebuild_default():
    """IrAst(IrCollection) inherits __call__: rebuild with called rules."""
    empty = IrAst(rules=(), start="r")
    result: IrAst = empty(IrNone, IrNone, ())
    assert isinstance(result, IrAst)
    if isinstance(
        result, IrAst
    ):  # Pylint can't infer the type here, but we know it must be IrAst.
        assert not result.rules
        assert result.start == "r"


def test_irgroup_call_inherits_rebuild_default():
    """IrGroup(IrComposite) inherits __call__ via rebuild(called children)."""
    g = IrGroup(body=IrAlternation())
    result = g(IrNone, IrNone, ())
    assert isinstance(result, IrGroup)
    assert isinstance(result.body, IrAlternation)
