"""IR AST node dataclasses — frozen, hashable, immutable tuples."""

from __future__ import annotations

import pytest

from lexic.ir.nodes_2 import (
    IrAlternation,
    IrAst,
    IrAtom,
    IrCharClass,
    IrComposite,
    IrGroup,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrNode,
    IrNone,
    IrNoneType,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrStr,
    IrTuple,
)

# ── IrQuantifier ───────────────────────────────────────────────────────


def test_quantifier_default_is_one_one():
    """Test that the default quantifier has min=1 and max=1."""
    q = IrQuantifier()
    assert q.min == 1 and q.max == 1


def test_quantifier_unbounded_max_is_none():
    """Test that the unbounded quantifier has max=None."""
    q = IrQuantifier(min=1, max=None)
    assert q.max is None


def test_quantifier_is_frozen():
    """Frozen dataclass rejects attribute mutation."""
    q = IrQuantifier(0, 1)
    with pytest.raises(AttributeError):
        setattr(q, "min", 5)


def test_quantifier_is_hashable():
    """Equal quantifiers are deduplicated in a set."""
    assert len({IrQuantifier(0, 1), IrQuantifier(0, 1)}) == 1


# ── Leaves ───────────────────────────────────────────────────────────


def test_ir_literal_holds_canonical_value():
    """Test that the IR literal holds a canonical value."""
    lit = IrLiteral("hello")
    assert lit == "hello"


def test_ir_literal_canonical_python_newline():
    """Test that the IR literal holds a canonical Python newline."""
    lit = IrLiteral("a\nb")
    assert lit == "a\nb"


def test_ir_literal_is_frozen_and_hashable():
    """Str leaves are hashable and deduplicate in sets."""
    assert len({IrLiteral("a"), IrLiteral("a")}) == 1


def test_ir_charclass_holds_pattern():
    """Test that the IR character class holds the pattern."""
    cc = IrCharClass("a-z")
    assert cc == "a-z"


def test_ir_not_wraps_charclass():
    """Test that IrNot wraps a charclass atom."""
    cc = IrCharClass("\\n")
    node = IrNot[IrCharClass](body=cc)
    assert node.body is cc
    assert node.body == "\\n"


def test_ir_ruleref_holds_name():
    """Test that the IR rule reference holds the correct name."""
    r = IrRuleRef("expr")
    assert r == "expr"


# ── IrItem ───────────────────────────────────────────────────────────


def test_ir_item_default_quantifier():
    """Test that the IR item has the correct default quantifier."""
    it = IrItem(atom=IrLiteral("x"))
    assert it.quantifier == IrQuantifier()


def test_ir_item_with_explicit_quantifier():
    """Test that the IR item can have an explicit quantifier."""
    it = IrItem(atom=IrCharClass("a-z"), quantifier=IrQuantifier(0, None))
    assert it.quantifier.min == 0
    assert it.quantifier.max is None


def test_ir_item_atom_can_be_group():
    """Test that the IR item can have a group as its atom."""
    grp = IrGroup(IrAlternation(IrSequence(IrItem(IrLiteral("a")))))
    it = IrItem(atom=grp, quantifier=IrQuantifier(1, None))
    assert isinstance(it.atom, IrGroup)


# ── Structure ────────────────────────────────────────────────────────


def test_ir_sequence_items_are_tuple():
    """Test that the IR sequence holds its items in a tuple."""
    seq = IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
    assert isinstance(seq, tuple)
    assert len(seq) == 2


def test_ir_alternation_arms_are_tuple():
    """Test that the IR alternation holds its arms in a tuple."""
    alt = IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    assert isinstance(alt, tuple)


def test_ir_group_wraps_alternation():
    """An IR group should wrap an IrAlternation body."""
    alt = IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    grp = IrGroup(body=alt)
    assert grp.body is alt


def test_ir_rule_has_alternation_body():
    """An IR rule should have a body that is an IrAlternation, even if single-arm."""
    body = IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    rule = IrRule("r", body=body)
    assert rule.name == "r"
    assert rule.body is body


def test_ir_ast_holds_rules_and_start():
    """An IR AST should hold a tuple of rules and the name of the start rule."""
    body = IrAlternation(IrSequence())
    rule = IrRule("root", body=body)
    ast = IrAst(IrTuple(rule), "root")
    assert ast.start == "root"
    assert ast.rules == (rule,)


def test_ir_ast_is_frozen():
    """Frozen dataclass rejects attribute mutation on IrAst."""
    ast = IrAst(IrTuple(), "root")
    with pytest.raises(AttributeError):
        setattr(ast, "start", "other")


# ── Equality ─────────────────────────────────────────────────────────


def test_structurally_equal_asts_compare_equal():
    """Two IR ASTs with the same structure and values should compare equal."""
    a = IrAst(
        IrTuple(
            IrRule(
                "r",
                IrAlternation(IrSequence(IrItem(IrLiteral("x")))),
            ),
        ),
        "r",
    )
    b = IrAst(
        IrTuple(
            IrRule(
                "r",
                IrAlternation(IrSequence(IrItem(IrLiteral("x")))),
            ),
        ),
        "r",
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
        IrQuantifier,
    ):
        assert issubclass(cls, IrNode), f"{cls.__name__} must inherit IrNode"


def test_irnode_default_children_is_empty_tuple():
    """Leaves inherit empty-tuple default."""
    assert not IrLiteral("x").children()
    assert not IrCharClass("a-z").children()
    assert not IrRuleRef("foo").children()
    assert not IrQuantifier().children()


def test_irnode_default_rebuild_is_identity():
    """Leaves inherit identity rebuild."""
    leaf = IrLiteral("x")
    assert leaf.rebuild(()) is leaf


def test_iritem_children_returns_atom_and_quantifier():
    """An IrItem's children are its atom and quantifier."""
    item = IrItem(IrLiteral("x"), IrQuantifier(0, None))
    assert tuple(item.children()) == (item.atom, item.quantifier)


def test_iritem_rebuild_replaces_atom_and_quantifier():
    """Rebuilding an IrItem replaces both atom and quantifier from new_children."""
    item = IrItem(IrLiteral("x"), IrQuantifier(0, None))
    new = item.rebuild((IrLiteral("y"), IrQuantifier(1, 3)))
    assert new == IrItem(IrLiteral("y"), IrQuantifier(1, 3))


def test_irsequence_children_returns_items():
    """An IrSequence's children are its items."""
    a, b = IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))
    seq = IrSequence(a, b)
    assert tuple(seq.children()) == (a, b)


def test_irsequence_rebuild_replaces_items():
    """Rebuilding an IrSequence replaces its items."""
    a, b = IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))
    seq = IrSequence(a)
    assert seq.rebuild((a, b)) == IrSequence(a, b)


def test_iralternation_children_returns_arms():
    """An IrAlternation's children are its arms."""
    s = IrSequence()
    alt = IrAlternation(s)
    assert tuple(alt.children()) == (s,)


def test_iralternation_rebuild_replaces_arms():
    """Rebuilding an IrAlternation replaces its arms."""
    s1, s2 = IrSequence(), IrSequence()
    assert IrAlternation(s1).rebuild((s1, s2)) == IrAlternation(s1, s2)


def test_irgroup_children_returns_body():
    """An IrGroup's children are its body."""
    body = IrAlternation()
    grp = IrGroup(body)
    assert tuple(grp.children()) == (body,)


def test_irgroup_rebuild_replaces_body():
    """Rebuilding an IrGroup replaces its body."""
    b1, b2 = IrAlternation(), IrAlternation(IrSequence())
    assert IrGroup(b1).rebuild((b2,)) == IrGroup(b2)


def test_irrule_children_returns_body():
    """An IrRule's children are its body."""
    body = IrAlternation()
    rule = IrRule("r", body)
    assert tuple(rule.children()) == (body,)


def test_irrule_rebuild_replaces_body_preserves_name():
    """Rebuilding an IrRule replaces its body but preserves the name."""
    b1, b2 = IrAlternation(), IrAlternation(IrSequence())
    assert IrRule("r", b1).rebuild((b2,)) == IrRule("r", b2)


def test_irast_children_returns_rules_tuple():
    """An IrAst's children are the wrapping rules IrTuple (G3 shape change).

    Old ``IrCollection`` returned the rules directly; new ``IrComposite``
    returns a 1-tuple wrapping the rules ``IrTuple`` — iterate ``ast.rules``
    to reach individual rules.
    """
    r = IrRule("x", IrAlternation())
    ast = IrAst(IrTuple(r), "x")
    assert tuple(ast.children()) == (IrTuple(r),)
    assert ast.rules == (r,)


def test_irast_rebuild_replaces_rules_preserves_start():
    """Rebuilding an IrAst replaces its rules but preserves the start name."""
    r1 = IrRule("a", IrAlternation())
    r2 = IrRule("b", IrAlternation())
    rebuilt = IrAst(IrTuple(r1), "a").rebuild((IrTuple(r1, r2),))
    assert rebuilt == IrAst(IrTuple(r1, r2), "a")


def test_repr_irliteral_is_codegen():
    """An IrLiteral's repr reproduces its constructor call."""
    assert repr(IrLiteral("a")) == "IrLiteral('a')"


def test_repr_irsequence_is_codegen():
    """An IrSequence's repr reproduces its constructor call."""
    seq = IrSequence(IrItem(IrLiteral("a")))
    assert repr(seq) == (
        "IrSequence(IrItem(atom=IrLiteral('a'), quantifier=IrQuantifier(min=1, max=1)))"
    )


def test_repr_irrule_shows_non_child_fields_too():
    """name appears alongside the recursed body."""
    rule = IrRule("r", IrAlternation())
    assert repr(rule) == "IrRule(name='r', body=IrAlternation())"


def test_repr_empty_structural_node_is_codegen():
    """An empty structural node reproduces its constructor call."""
    assert repr(IrSequence()) == "IrSequence()"
    assert repr(IrAlternation()) == "IrAlternation()"


def test_repr_irgroup_is_codegen():
    """IrGroup reproduces its constructor call."""
    grp = IrGroup(IrAlternation())
    assert repr(grp) == "IrGroup(body=IrAlternation())"


def test_repr_irast_is_codegen():
    """IrAst reproduces its constructor call."""
    ast = IrAst(IrTuple(IrRule("r", IrAlternation())), "r")
    assert repr(ast) == (
        "IrAst(rules=IrTuple(IrRule(name='r', body=IrAlternation())), start='r')"
    )


def test_irliteral_eval_returns_literal_value():
    """IrLiteral surfaces itself (the string) as a str via ``eval``.

    ``__call__`` remains identity (returns self) via :class:`IrSelf`;
    ``eval`` is the value-producing protocol.
    """
    lit = IrLiteral("hello")
    result: str = lit.eval(IrNone, IrNone, ())
    assert result == "hello"


def test_ircharclass_call_inherits_identity_default():
    """IrCharClass(IrStr) inherits the default __call__ — returns self."""
    cc = IrCharClass("a-z")
    result = cc(IrNone, IrNone, ())
    assert result is cc


def test_irruleref_call_inherits_identity_default():
    """IrRuleRef(IrStr) inherits the default __call__ — returns self."""
    ref = IrRuleRef("foo")
    assert ref(IrNone, IrNone, ()) is ref


def test_irast_call_inherits_identity_default():
    """IrAst inherits the default __call__ — returns self."""
    empty = IrAst(IrTuple(), "r")
    result = empty(IrNone, IrNone, ())
    assert isinstance(result, IrAst)
    assert not result.rules
    assert result.start == "r"


def test_irgroup_call_inherits_identity_default():
    """IrGroup inherits the default __call__ — returns self."""
    g = IrGroup(body=IrAlternation())
    result = g(IrNone, IrNone, ())
    assert isinstance(result, IrGroup)
    assert isinstance(result.body, IrAlternation)


# ── Contract tests (plan Tasks 1–4) ──────────────────────────────────


def test_irself_identity_call_returns_self():
    class L(IrLeaf):
        __slots__ = ()

        def __repr__(self) -> str:
            return "L()"

    leaf = L()
    assert leaf(IrNone, IrNone, ()) is leaf


def test_irnone_is_final_singleton_and_is_irself():
    assert IrNone is IrNoneType()  # public value IS the singleton instance
    assert isinstance(IrNone, (IrSelf, IrNoneType))
    # @final is a STATIC-only guarantee (pyright flags subclassing); no runtime raise.


def test_iratom_is_non_generic_marker():
    # IrAtom has no type parameters of its own
    assert getattr(IrAtom, "__type_params__", ()) == ()
    assert issubclass(IrAtom, IrNode)


def test_str_leaf_is_str_and_atom():
    lit = IrLiteral("x")
    assert isinstance(lit, str) and isinstance(lit, IrAtom)
    assert lit == "x"  # native str equality
    assert lit.upper() == "X"  # native str methods


def test_str_leaf_new_returns_own_subtype():
    # the -> Self bug guard: must NOT collapse to IrStr
    assert type(IrRuleRef("r")) is IrRuleRef
    assert isinstance(IrRuleRef("r"), IrAtom)


def test_str_leaf_repr_is_codegen():
    assert repr(IrLiteral("x")) == "IrLiteral('x')"
    assert repr(IrCharClass("0-9")) == "IrCharClass('0-9')"


def test_tuple_node_is_variadic_and_native_eq():
    seq = IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
    assert isinstance(seq, tuple) and isinstance(seq, IrNode)
    a, b = IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("b")))
    assert IrAlternation(a, b) == IrAlternation(a, b)
    assert IrAlternation(a, b) != IrAlternation(b, a)  # order is identity


def test_tuple_children_and_rebuild_roundtrip():
    p, q, r = (
        IrSequence(IrItem(IrLiteral("p"))),
        IrSequence(IrItem(IrLiteral("q"))),
        IrSequence(IrItem(IrLiteral("r"))),
    )
    alt = IrAlternation(p, q)
    assert tuple(alt.children()) == (p, q)
    assert alt.rebuild((r,)) == IrAlternation(r)


def test_tuple_repr_is_codegen():
    assert repr(IrSequence(IrItem(IrLiteral("a")))) == (
        "IrSequence(IrItem(atom=IrLiteral('a'), quantifier=IrQuantifier(min=1, max=1)))"
    )


def test_quantifier_plain_int_fields():
    q = IrQuantifier(0, None)
    assert (q.min, q.max) == (0, None)
    assert IrQuantifier(1, 1) == IrQuantifier(1, 1)  # frozen dataclass eq


def test_item_accepts_atom_subclasses():
    it = IrItem(IrLiteral("x"))  # IrLiteral IS-A IrAtom
    assert it.atom == "x"
    assert isinstance(it.quantifier, IrQuantifier)
    assert tuple(it.children()) == (it.atom, it.quantifier)


def test_group_and_not_are_atoms():
    body = IrAlternation(IrSequence())
    assert isinstance(IrGroup(body), IrAtom)
    assert isinstance(IrNot(IrLiteral("a")), IrAtom)


def test_composite_repr_is_codegen():
    assert (
        repr(IrRule("r", IrAlternation())) == "IrRule(name='r', body=IrAlternation())"
    )


def test_composite_is_dataclass_base():
    assert isinstance(IrQuantifier(0, 1), IrComposite)
    assert isinstance(IrItem(IrLiteral("x")), IrComposite)


# ── _bound derivation (own __type_params__ only; explicit wins; never MRO) ──


def test_bound_explicit_declaration_wins():
    """A class-level ``_bound`` (IrStr/IrTuple) is kept verbatim, not derived."""
    assert IrStr._bound is str
    assert IrTuple._bound is tuple


def test_bound_inherited_explicit_is_not_reclobbered_via_mro():
    """A subclass with no OWN type params keeps the inherited explicit ``_bound``.

    This guards the precise attempt-0 root cause: an MRO walk would re-derive
    ``IrSequence._bound`` as ``IrSelf`` (from ``IrTuple``'s ``T: IrSelf`` param).
    The own-``__type_params__``-only rule must leave it as the inherited ``tuple``.
    """
    assert IrSequence._bound is tuple
    assert IrAlternation._bound is tuple
    assert IrLiteral._bound is str
    assert IrCharClass._bound is str
    assert IrRuleRef._bound is str


def test_bound_derived_from_own_typevar_bound():
    """A class with its OWN bounded TypeVar derives ``_bound`` from that bound."""
    assert IrNot._bound is IrAtom  # IrNot[Ir_co: IrAtom] -> IrAtom

    class _Probe[T: IrLiteral](IrComposite):  # own bounded TypeVar -> derived
        pass

    assert _Probe._bound is IrLiteral
