# Test files may exceed max-module-lines (user ruling, 2026-07-04). Splitting
# this one is not available either: the mirror gate in
# tests/integration/lexic/invariants/test_test_parity.py pins one test file
# per source module, so a second half would have to be exempted from a real
# invariant to satisfy a line count.
# pylint: disable=too-many-lines
"""IR AST node dataclasses — frozen, hashable, immutable tuples."""

from __future__ import annotations

import pytest

from lexic.compile import parse_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir.grammar.charclass import IrCharClass, IrRange
from lexic.ir.grammar.nodes import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrBounds,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.grammar.operators import IrNot
from lexic.ir.spine.records import IrNamedTuple, IrSeq
from lexic.ir.spine.scalars import IrChr, IrInt, IrStr
from lexic.ir.spine.spine import IrAtom, IrNode, IrNone, IrNoneType

# ── IrQuantifier ───────────────────────────────────────────────────────


def test_quantifier_default_is_one_one():
    """Test that the default quantifier has lo=1 and hi=1."""
    q = IrQuantifier()
    assert q.lo == 1 and q.hi == 1


def test_quantifier_unbounded_max_is_none():
    """Test that the unbounded quantifier has hi=IrNone."""
    q = IrQuantifier(lo=1, hi=IrNone)
    assert q.hi is IrNone


def test_quantifier_is_frozen():
    """Frozen record rejects attribute mutation."""
    q = IrQuantifier(0, 1)
    with pytest.raises(AttributeError):
        setattr(q, "lo", 5)


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
    """Test that the IR character class holds the pattern via charclass_pattern."""
    cc = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    assert cc.pattern() == "a-z"


def test_ir_not_wraps_charclass():
    """Test that IrNot wraps a charclass atom."""
    cc = IrCharClass(IrChr("\n"))
    node = IrNot(cc)
    assert node[0] is cc
    inner = node[0]
    assert isinstance(inner, IrCharClass)
    assert inner.pattern() == "\\x0a"


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
    it = IrItem(
        atom=IrCharClass(IrRange(IrChr("a"), IrChr("z"))),
        quantifier=IrQuantifier(0, IrNone),
    )
    assert it.quantifier.lo == 0
    assert it.quantifier.hi is IrNone


def test_ir_item_atom_can_be_alternation_group():
    """Test that the IR item can have an alternation (group) as its atom."""
    grp = IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    it = IrItem(atom=grp, quantifier=IrQuantifier(1, IrNone))
    assert isinstance(it.atom, IrAlternation)


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
    ast = IrAst(IrSeq(rule), "root")
    assert ast.start == "root"
    assert ast.rules == IrSeq(rule)


def test_ir_ast_is_frozen():
    """Frozen dataclass rejects attribute mutation on IrAst."""
    ast = IrAst(IrSeq(), "root")
    with pytest.raises(AttributeError):
        setattr(ast, "start", "other")


# ── Equality ─────────────────────────────────────────────────────────


def test_structurally_equal_asts_compare_equal():
    """Two IR ASTs with the same structure and values should compare equal."""
    a = IrAst(
        IrSeq(
            IrRule(
                "r",
                IrAlternation(IrSequence(IrItem(IrLiteral("x")))),
            ),
        ),
        "r",
    )
    b = IrAst(
        IrSeq(
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
        IrLiteral,
        IrCharClass,
        IrRuleRef,
        IrQuantifier,
    ):
        assert issubclass(cls, IrNode), f"{cls.__name__} must inherit IrNode"


def test_irnode_default_children_is_empty_tuple():
    """Str-leaves and quantifier inherit empty-tuple default.

    IrCharClass has elements as children.
    """
    assert not IrLiteral("x").children()
    assert not IrRuleRef("foo").children()
    assert not IrQuantifier().children()
    # IrCharClass is a variadic IrSeq — its elements are its children
    assert tuple(IrCharClass(IrRange(IrChr("a"), IrChr("z"))).children()) == (
        IrRange(IrChr("a"), IrChr("z")),
    )


def test_irnode_default_rebuild_is_identity():
    """Leaves inherit identity rebuild."""
    leaf = IrLiteral("x")
    assert leaf.rebuild(()) is leaf


def test_iritem_children_returns_atom_and_quantifier():
    """An IrItem's children are its atom and quantifier."""
    item = IrItem(IrLiteral("x"), IrQuantifier(0, IrNone))
    assert tuple(item.children()) == (item.atom, item.quantifier)


def test_iritem_rebuild_replaces_atom_and_quantifier():
    """Rebuilding an IrItem replaces both atom and quantifier from new_children."""
    item = IrItem(IrLiteral("x"), IrQuantifier(0, IrNone))
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

    ``IrNamedTuple``
    returns a 1-tuple wrapping the rules ``IrTuple`` — iterate ``ast.rules``
    to reach individual rules.
    """
    r = IrRule("x", IrAlternation())
    ast = IrAst(IrSeq(r), "x")
    assert tuple(ast.children()) == (IrSeq(r),)
    assert ast.rules == IrSeq(r)


def test_irast_rebuild_replaces_rules_preserves_start():
    """Rebuilding an IrAst replaces its rules but preserves the start name."""
    r1 = IrRule("a", IrAlternation())
    r2 = IrRule("b", IrAlternation())
    rebuilt = IrAst(IrSeq(r1), "a").rebuild((IrSeq(r1, r2),))
    assert rebuilt == IrAst(IrSeq(r1, r2), "a")


def test_repr_irliteral_is_codegen():
    """An IrLiteral's repr reproduces its constructor call."""
    assert repr(IrLiteral("a")) == "IrLiteral('a')"


def test_repr_irsequence_is_codegen():
    """An IrSequence's repr reproduces its constructor call.

    The default-valued quantifier ``IrQuantifier(1, 1)`` is a trailing default
    and is omitted from the nested ``IrItem``'s repr.
    """
    seq = IrSequence(IrItem(IrLiteral("a")))
    assert repr(seq) == "IrSequence(IrItem(IrLiteral('a')))"


def test_repr_irrule_shows_non_child_fields_too():
    """name appears alongside the recursed body."""
    rule = IrRule("r", IrAlternation())
    assert repr(rule) == "IrRule('r', IrAlternation())"


def test_repr_empty_structural_node_is_codegen():
    """An empty structural node reproduces its constructor call."""
    assert repr(IrSequence()) == "IrSequence()"
    assert repr(IrAlternation()) == "IrAlternation()"


def test_repr_irast_is_codegen():
    """IrAst reproduces its constructor call.

    ``IrAst`` has two fields (``rules``, ``start``) — ``non_semantic`` is a
    derived read-only property, not a field, so it never appears in the repr.
    """
    ast = IrAst(IrSeq(IrRule("r", IrAlternation())), "r")
    assert repr(ast) == "IrAst(IrSeq(IrRule('r', IrAlternation())), 'r')"


def test_irliteral_eval_returns_literal_value():
    """IrLiteral surfaces itself (the string) as a str via ``eval``.

    ``__call__`` remains identity (returns self) via :class:`IrSelf`;
    ``eval`` is the value-producing protocol.
    """
    lit = IrLiteral("hello")
    result = lit.eval(IrNone, IrNone, ())
    assert result == "hello"
    assert isinstance(result, str)


def test_ircharclass_call_inherits_identity_default():
    """IrCharClass(IrStr) inherits the default __call__ — returns self."""
    cc = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    result = cc(IrNone, IrNone, ())
    assert result is cc


def test_irruleref_call_inherits_identity_default():
    """IrRuleRef(IrStr) inherits the default __call__ — returns self."""
    ref = IrRuleRef("foo")
    assert ref(IrNone, IrNone, ()) is ref


def test_irast_call_inherits_identity_default():
    """IrAst inherits the default __call__ — returns self."""
    empty = IrAst(IrSeq(), "r")
    result = empty(IrNone, IrNone, ())
    assert isinstance(result, IrAst)
    assert not result.rules
    assert result.start == "r"


# ── Contract tests (plan Tasks 1–4) ──────────────────────────────────


def test_str_leaf_is_str_and_atom():
    """IrLiteral is simultaneously a str and an IrAtom — no wrapper boxing."""
    lit = IrLiteral("x")
    assert isinstance(lit, str) and isinstance(lit, IrAtom)
    assert lit == "x"  # native str equality
    assert lit.upper() == "X"  # native str methods


def test_str_leaf_new_returns_own_subtype():
    """IrRuleRef.__new__ returns IrRuleRef, not the IrStr base — Self is preserved."""
    # the -> Self bug guard: must NOT collapse to IrStr
    assert isinstance(IrRuleRef("r"), IrRuleRef)
    assert isinstance(IrRuleRef("r"), IrAtom)


def test_str_leaf_repr_is_codegen():
    """repr() on str-leaves reproduces the constructor call.

    IrCharClass is now a variadic IrSeq; its repr uses the structured elements.
    IrChr endpoints are stored as integer ordinals, so their repr is IrChr(n).
    """
    assert repr(IrLiteral("x")) == "IrLiteral('x')"
    assert (
        repr(IrCharClass(IrRange(IrChr("0"), IrChr("9"))))
        == "IrCharClass(IrRange(IrChr(48), IrChr(57)))"
    )


def test_tuple_node_is_variadic_and_native_eq():
    """IrSequence is both a tuple and an IrNode; IrAlternation equality is order-sensitive."""
    seq = IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
    assert isinstance(seq, tuple) and isinstance(seq, IrNode)
    a, b = IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("b")))
    assert IrAlternation(a, b) == IrAlternation(a, b)
    assert IrAlternation(a, b) != IrAlternation(b, a)  # order is identity


def test_tuple_children_and_rebuild_roundtrip():
    """IrAlternation.children() yields arms; rebuild() splices in new arms."""
    p, q, r = (
        IrSequence(IrItem(IrLiteral("p"))),
        IrSequence(IrItem(IrLiteral("q"))),
        IrSequence(IrItem(IrLiteral("r"))),
    )
    alt = IrAlternation(p, q)
    assert tuple(alt.children()) == (p, q)
    assert alt.rebuild((r,)) == IrAlternation(r)


def test_tuple_repr_is_codegen():
    """repr() on an IrSequence reproduces the constructor call.

    The nested ``IrItem``'s default quantifier is a trailing default and is
    omitted.
    """
    assert (
        repr(IrSequence(IrItem(IrLiteral("a")))) == "IrSequence(IrItem(IrLiteral('a')))"
    )


def test_quantifier_plain_int_fields():
    """IrQuantifier stores lo/hi; IrNone as upper bound; frozen record equality applies."""
    q = IrQuantifier(0, IrNone)
    assert (q.lo, q.hi) == (0, IrNone)
    assert q.hi is IrNone
    assert IrQuantifier(1, 1) == IrQuantifier(1, 1)  # frozen record eq


def test_quantifier_coerces_irint_endpoints_to_plain_int():
    """IrQuantifier narrows IrInt-typed endpoints to plain int at construction
    (repr-is-codegen must never emit 'IrInt(...)' into generated modules)."""
    q = IrQuantifier(IrInt(2), IrInt(5))
    assert isinstance(q.lo, int) and not isinstance(q.lo, IrInt)
    assert isinstance(q.hi, int) and not isinstance(q.hi, IrInt)
    assert q == IrQuantifier(2, 5)
    assert "IrInt" not in repr(q)


def test_quantifier_coerces_irint_lo_keeps_irnone_hi():
    """An IrInt lower bound narrows to int while an unbounded IrNone upper
    bound is left untouched."""
    q = IrQuantifier(IrInt(0), IrNone)
    assert isinstance(q.lo, int) and not isinstance(q.lo, IrInt)
    assert q.hi is IrNone


def test_item_accepts_atom_subclasses():
    """IrItem wraps any IrAtom subclass; children() yields (atom, quantifier)."""
    it = IrItem(IrLiteral("x"))  # IrLiteral IS-A IrAtom
    assert it.atom == "x"
    assert isinstance(it.quantifier, IrQuantifier)
    assert tuple(it.children()) == (it.atom, it.quantifier)


def test_alternation_and_not_are_atoms():
    """IrAlternation (group) and IrNot are IrAtom instances — usable as IrItem.atom."""
    assert isinstance(IrAlternation(IrSequence()), IrAtom)
    assert isinstance(IrNot(IrLiteral("a")), IrAtom)


def test_composite_repr_is_codegen():
    """repr() on IrRule reproduces the constructor call."""
    assert repr(IrRule("r", IrAlternation())) == "IrRule('r', IrAlternation())"


def test_all_grammar_records_are_named_tuples():
    """Every grammar-AST record is now an IrNamedTuple (IrNamedTuple fully folded)."""
    for node in (
        IrQuantifier(),
        IrItem(IrLiteral("x")),
        IrRule("r", IrAlternation()),
        IrAst(),
    ):
        assert isinstance(node, IrNamedTuple)


# ── _bound derivation (own __type_params__ only; explicit wins; never MRO) ──


def test_bound_inherited_explicit_is_not_reclobbered_via_mro():
    """A subclass with no OWN type params keeps the inherited explicit ``_bound``.

    This guards the precise attempt-0 root cause: an MRO walk would re-derive
    ``IrSequence._bound`` as ``IrSelf`` (from ``IrTuple``'s ``T: IrSelf`` param).
    The own-``__type_params__``-only rule must leave it as the inherited ``tuple``.
    ``IrCharClass`` is now a variadic ``IrSeq``, so its bound is ``tuple``.
    """
    assert IrSequence.bound_type() is tuple
    assert IrAlternation.bound_type() is tuple
    assert IrLiteral.bound_type() is str
    assert IrCharClass.bound_type() is tuple
    assert IrRuleRef.bound_type() is str


def test_bound_derived_from_own_typevar_bound():
    """A class with its OWN bounded TypeVar derives ``_bound`` from that bound."""

    class _Probe[T: IrLiteral](IrNode):  # own bounded TypeVar -> derived
        pass

    assert _Probe.bound_type() is IrLiteral


# ── Concrete str-leaf kinds ───────────────────────────────────────────
# (IrScalar/IrInt spine behaviour lives in test_base.py)


def test_irscalar_eq_is_type_aware_across_kinds():
    """Distinct concrete value-leaf kinds never compare equal, same payload or not."""
    assert IrLiteral("x") != IrRuleRef("x")  # distinct str-leaf kinds
    assert IrInt(5) != IrLiteral("5")  # int leaf vs str leaf
    assert len({IrLiteral("a"), IrLiteral("a"), IrRuleRef("a")}) == 2


# ── IrRange (step 1) ─────────────────────────────────────────────────


def test_irrange_construction_and_fields():
    """IrRange stores IrChr lo/hi as accessible fields."""
    r = IrRange(IrChr("a"), IrChr("z"))
    assert r.lo == IrChr("a")
    assert r.hi == IrChr("z")


def test_irrange_children_is_empty():
    """IrRange has _child_attrs=() — walkers never descend into bounds."""
    assert not IrRange(IrChr("a"), IrChr("z")).children()


def test_irrange_positional_access():
    """IrRange is a named tuple — positional indexing works."""
    r = IrRange(IrChr("a"), IrChr("z"))
    assert r[0] == IrChr("a")
    assert r[1] == IrChr("z")


def test_irrange_repr_is_codegen():
    """repr(IrRange(...)) reproduces the constructor call over code points."""
    assert repr(IrRange(IrChr("a"), IrChr("z"))) == "IrRange(IrChr(97), IrChr(122))"


def test_irquantifier_repr_with_irnone():
    """repr(IrQuantifier(0, IrNone)) renders the sentinel, not Python None."""
    assert repr(IrQuantifier(0, IrNone)) == "IrQuantifier(0, IrNone)"


def test_irnone_repr():
    """repr(IrNone) returns 'IrNone' — the codegen repr."""
    assert repr(IrNone) == "IrNone"


def test_irquantifier_and_irrange_are_disjoint_siblings():
    """IrQuantifier and IrRange are siblings under IrBounds — neither IS-A the other."""
    assert not isinstance(IrQuantifier(), IrRange)
    assert not isinstance(IrRange(IrChr("a"), IrChr("z")), IrQuantifier)
    assert not issubclass(IrQuantifier, IrRange)
    assert issubclass(IrQuantifier, IrBounds)
    assert issubclass(IrRange, IrBounds)


def test_bounds_equality_is_type_aware():
    """A count range and a same-numbered code-point range never compare equal."""
    assert IrQuantifier(65, 90) != IrRange(IrChr(65), IrChr(90))
    assert IrQuantifier(1, 1) == IrQuantifier(1, 1)
    assert IrRange(IrChr("A"), IrChr("Z")) == IrRange(IrChr(0x41), IrChr(0x5A))


def test_bounds_are_hashable():
    """Defining __eq__ does not break hashability — bounds work as set/dict keys."""
    r = IrRange(IrChr(65), IrChr(90))
    assert r in {r}
    assert hash(IrQuantifier(1, 1)) == hash(IrQuantifier(1, 1))


def test_quantifier_membership():
    """`value in quantifier` tests the count range; IrNone hi is unbounded above."""
    assert 5 in IrQuantifier(1, 10)
    assert 11 not in IrQuantifier(1, 10)
    assert 100 in IrQuantifier(1, IrNone)  # open upper bound is unbounded


def test_range_membership():
    """`codepoint in range` tests the inclusive code-point span."""
    assert IrChr(0x42) in IrRange(IrChr(0x41), IrChr(0x5A))
    assert IrChr(0x60) not in IrRange(IrChr(0x41), IrChr(0x5A))


def test_quantifier_defaults_to_one_one():
    """IrQuantifier() defaults to the exactly-once (1, 1) bound."""
    assert IrQuantifier() == IrQuantifier(1, 1)


def test_range_requires_endpoints():
    """IrRange endpoints are required — no NUL placeholder default."""
    no_args: list[IrChr] = []
    with pytest.raises(TypeError):
        IrRange(*no_args)


def test_irnone_is_irnonetype_instance():
    """IrNone is an instance of IrNoneType."""
    assert isinstance(IrNone, IrNoneType)


def test_charclass_holds_codepoints_and_ranges():
    """IrCharClass is the variadic union of IrChr code points and IrRange spans."""
    cc = IrCharClass(IrChr(0x41), IrRange(IrChr(0x30), IrChr(0x39)))
    assert cc[0] == IrChr(0x41)
    assert cc[1] == IrRange(IrChr(0x30), IrChr(0x39))


# ── Constructor coercion (ast_sugar, Task 0) ────────────────────────────
#
# Unknown-type passthrough is exercised via `.rebuild()` rather than direct
# construction: `rebuild`'s parameter is typed `Sequence[IrSelf]`, so passing
# an off-menu IrSelf leaf (e.g. a bare IrStr) through it is pyright-clean,
# whereas the widened `__new__` signatures themselves are typed to the known
# union and would reject it statically.


def canonical_rule(name: str, atom: IrAtom) -> IrRule:
    """Hand-built canonical single-arm rule for a given atom."""
    return IrRule(name, IrAlternation(IrSequence(IrItem(atom))))


# -- IrSequence: bare-atom element wrapping --


def test_irsequence_coerces_bare_atom_to_unit_item():
    """A bare IrAtom element wraps to IrItem(atom) with the unit quantifier."""
    lit = IrLiteral("a")
    seq = IrSequence(lit)
    assert seq[0] == IrItem(lit)
    assert seq[0].quantifier == IrQuantifier()


def test_irsequence_keeps_item_element_as_is():
    """An IrItem element passed to IrSequence is kept, not re-wrapped."""
    item = IrItem(IrLiteral("a"), IrQuantifier(0, IrNone))
    seq = IrSequence(item)
    assert seq[0] is item


def test_irsequence_unknown_element_passes_through():
    """An off-menu element (a bare IrStr, reached via rebuild) is untouched."""
    seq = IrSequence(IrItem(IrLiteral("a")))
    raw = IrStr("raw")
    rebuilt = seq.rebuild((raw,))
    assert rebuilt[0] is raw


# -- IrAlternation: bare-arm sequence wrapping --


def test_iralternation_coerces_bare_atom_arm_via_sequence():
    """A bare IrAtom arm wraps via IrSequence (whose own coercion lifts it)."""
    lit = IrLiteral("a")
    alt = IrAlternation(lit)
    assert alt[0] == IrSequence(IrItem(lit))


def test_iralternation_coerces_bare_item_arm_via_sequence():
    """A bare IrItem arm wraps via IrSequence."""
    item = IrItem(IrLiteral("a"))
    alt = IrAlternation(item)
    assert alt[0] == IrSequence(item)


def test_iralternation_keeps_sequence_arm_as_is():
    """An IrSequence arm passed to IrAlternation is kept, not re-wrapped."""
    seq = IrSequence(IrItem(IrLiteral("a")))
    alt = IrAlternation(seq)
    assert alt[0] is seq


def test_iralternation_wraps_nested_alternation_as_single_item_group_arm():
    """A nested IrAlternation arm (IS-A IrAtom) becomes a single-item group arm."""
    inner = IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    alt = IrAlternation(inner)
    assert alt[0] == IrSequence(IrItem(inner))
    assert isinstance(alt[0][0].atom, IrAlternation)


def test_iralternation_unknown_arm_passes_through():
    """An off-menu arm (a bare IrStr, reached via rebuild) is untouched."""
    alt = IrAlternation(IrSequence())
    raw = IrStr("raw")
    rebuilt = alt.rebuild((raw,))
    assert rebuilt[0] is raw


# -- IrItem (D2): bare-sequence atom wrapping --


def test_iritem_coerces_bare_sequence_atom_to_alternation():
    """A bare IrSequence atom wraps to IrAlternation(seq) — the inline-group sugar."""
    seq = IrSequence(IrItem(IrLiteral("a")))
    item = IrItem(seq)
    assert item.atom == IrAlternation(seq)
    assert isinstance(item.atom, IrAlternation)


def test_iritem_keeps_real_atom_as_is():
    """A real IrAtom passed to IrItem is kept, not re-wrapped."""
    lit = IrLiteral("a")
    item = IrItem(lit)
    assert item.atom is lit


def test_iritem_default_quantifier_preserved_when_only_atom_given():
    """Omitting the quantifier still yields the unit default, atom coercion aside."""
    item = IrItem(IrLiteral("a"))
    assert item.quantifier == IrQuantifier()


def test_iritem_unknown_atom_passes_through():
    """An off-menu atom (a bare IrStr, reached via rebuild) is untouched."""
    item = IrItem(IrLiteral("a"))
    raw = IrStr("raw")
    rebuilt = item.rebuild((raw, IrQuantifier()))
    assert rebuilt.atom is raw


# -- IrRule: body coercion up the atom -> item -> sequence -> alternation cascade --


def test_irrule_body_coercion_from_alternation():
    """An IrAlternation body is taken as-is."""
    body = IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    assert IrRule("x", body) == canonical_rule("x", IrLiteral("a"))


def test_irrule_body_coercion_from_sequence():
    """An IrSequence body wraps up to a single-arm alternation."""
    body = IrSequence(IrItem(IrLiteral("a")))
    assert IrRule("x", body) == canonical_rule("x", IrLiteral("a"))


def test_irrule_body_coercion_from_item():
    """An IrItem body wraps up to a single-arm alternation."""
    body = IrItem(IrLiteral("a"))
    assert IrRule("x", body) == canonical_rule("x", IrLiteral("a"))


def test_irrule_body_coercion_from_bare_atom():
    """A bare IrAtom body wraps all the way up to a single-arm alternation."""
    assert IrRule("x", IrLiteral("a")) == canonical_rule("x", IrLiteral("a"))


def test_irrule_body_alternation_branch_runs_before_atom_branch():
    """IrAlternation IS-A IrAtom; the IrAlternation isinstance check must run
    first so a multi-arm body is not re-wrapped into a single-arm group."""
    multi = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrLiteral("b"))),
    )
    rule = IrRule("x", multi)
    assert rule.body is multi


def test_irrule_body_unknown_passes_through():
    """An off-menu body (a bare IrStr, reached via rebuild) is untouched."""
    rule = IrRule("x", IrAlternation())
    raw = IrStr("raw")
    rebuilt = rule.rebuild((raw,))
    assert rebuilt.body is raw


# -- Idempotence: canonical parts round-trip through construction unchanged --


def test_coercion_is_idempotent_across_tiers():
    """Feeding already-canonical shapes back through their own constructor
    at every tier (item/sequence/alternation/rule) yields an equal object."""
    lit = IrLiteral("a")
    item = IrItem(lit)
    seq = IrSequence(item)
    alt = IrAlternation(seq)
    rule = IrRule("r", alt)
    assert IrItem(lit) == item
    assert IrSequence(*seq) == seq
    assert IrAlternation(*alt) == alt
    assert IrRule("r", alt) == rule


# -- Equality + repr: sugared construction equals hand-built canonical --


def test_sugared_rule_equals_and_reprs_as_hand_built_canonical():
    """A sugared single-arm rule equals, and reprs identically to, its
    hand-built canonical form (repr strings compared — no eval, per policy)."""
    sugared = IrRule("cr", IrCharClass(IrChr("\r")))
    canonical = canonical_rule("cr", IrCharClass(IrChr("\r")))
    assert sugared == canonical
    assert repr(sugared) == repr(canonical)


# -- Keyword construction --


def test_irrule_keyword_construction_coerces_identically():
    """IrRule(name=..., body=...) coerces the same as positional construction."""
    positional = IrRule("r", IrLiteral("x"))
    keyword = IrRule(name="r", body=IrLiteral("x"))
    assert positional == keyword


def test_iritem_keyword_construction_coerces_identically():
    """IrItem(atom=..., quantifier=...) coerces the same as positional construction."""
    seq = IrSequence(IrItem(IrLiteral("a")))
    positional = IrItem(seq, IrQuantifier(0, IrNone))
    keyword = IrItem(atom=seq, quantifier=IrQuantifier(0, IrNone))
    assert positional == keyword
    assert isinstance(keyword.atom, IrAlternation)


# ── IrAlphabet ─────────────────────────────────────────────────────────


def test_alphabet_is_an_atom():
    """An alphabet binding is an :class:`IrAtom`."""
    assert isinstance(IrAlphabet("gpt2", IrLiteral("<think>")), IrAtom)


def test_alphabet_wraps_a_text_form_literal():
    """A text-form token reuses ``IrLiteral`` as its inner atom."""
    a = IrAlphabet("gpt2", IrLiteral("<think>"))
    assert a.encoding == IrStr("gpt2")
    assert a.inner == IrLiteral("<think>")


def test_alphabet_wraps_an_id_form_charclass():
    """An id-form token reuses ``IrCharClass`` over the id ordinal."""
    a = IrAlphabet("gpt2", IrCharClass(IrChr(1000)))
    assert a.inner == IrCharClass(IrChr(1000))


def test_alphabet_composes_with_negation():
    """A negated token nests an ``IrNot`` as the inner atom."""
    a = IrAlphabet("gpt2", IrNot(IrLiteral("</think>")))
    assert isinstance(a.inner, IrNot)


def test_alphabet_encoding_name_is_wrapped_to_irstr():
    """The encoding name is stored as an ``IrStr`` reference."""
    assert isinstance(IrAlphabet("gpt2", IrLiteral("<think>")).encoding, IrStr)


def test_alphabet_rides_iritem():
    """Being an atom, an alphabet binding wraps in ``IrItem`` unchanged."""
    a = IrAlphabet("gpt2", IrLiteral("<think>"))
    assert IrItem(a).atom is a


def test_alphabet_children_are_the_inner_atom_only():
    """Only the inner atom is a walked child; the encoding is payload."""
    a = IrAlphabet("gpt2", IrLiteral("<think>"))
    assert list(a.children()) == [IrLiteral("<think>")]


def test_alphabet_rebuild_keeps_the_encoding():
    """``rebuild`` replaces the inner atom and preserves the encoding."""
    a = IrAlphabet("gpt2", IrCharClass(IrChr(0)))
    rebuilt = a.rebuild([IrCharClass(IrChr(9))])
    assert rebuilt == IrAlphabet("gpt2", IrCharClass(IrChr(9)))


def test_alphabet_equality_distinguishes_encoding():
    """Same inner, different encoding names compare unequal."""
    inner = IrCharClass(IrChr(0))
    assert IrAlphabet("a", inner) != IrAlphabet("b", inner)


def test_alphabet_repr_is_codegen():
    """The repr reproduces the constructor call."""
    a = IrAlphabet("gpt2", IrLiteral("<think>"))
    assert repr(a) == "IrAlphabet(IrStr('gpt2'), IrLiteral('<think>'))"


# ── derived arm facts ─────────────────────────────────────────────────────


def test_unit_ref_is_the_rule_a_unit_reference_names():
    """A plain reference names its rule — the same string a rule map keys on."""
    ref = IrItem(IrRuleRef("member")).unit_ref()
    assert isinstance(ref, IrRuleRef)
    assert ref == "member"


@pytest.mark.parametrize(
    "item",
    [
        IrItem(IrRuleRef("member"), IrQuantifier(0, IrNone)),
        IrItem(IrRuleRef("member"), IrQuantifier(0, 1)),
        IrItem(IrLiteral(",")),
        IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))),
    ],
)
def test_unit_ref_is_absent_for_a_quantified_reference_or_another_atom(item):
    """Only an exactly-once reference counts; absence is ``IrNone``."""
    assert item.unit_ref() is IrNone


def test_sole_arm_is_the_items_of_a_one_arm_rule():
    """A single-arm rule's arm, as its items in order."""
    rule = IrRule("pair", IrSequence(IrItem(IrLiteral("(")), IrItem(IrRuleRef("x"))))
    assert rule.sole_arm() == (IrItem(IrLiteral("(")), IrItem(IrRuleRef("x")))


def test_sole_arm_is_absent_for_a_rule_with_several_arms():
    """Two arms have no sole arm."""
    rule = IrRule(
        "value",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("arr"))), IrSequence(IrItem(IrRuleRef("num")))
        ),
    )
    assert rule.sole_arm() is IrNone


def test_sole_ref_is_the_rule_an_arm_of_one_unit_reference_names():
    """An arm that is one exactly-once reference IS that rule's arm."""
    ref = IrSequence(IrItem(IrRuleRef("member"))).sole_ref()
    assert isinstance(ref, IrRuleRef)
    assert ref == "member"


@pytest.mark.parametrize(
    "arm",
    [
        IrSequence(IrItem(IrRuleRef("member"), IrQuantifier(0, IrNone))),
        IrSequence(IrItem(IrRuleRef("member"), IrQuantifier(1, IrNone))),
        IrSequence(IrItem(IrRuleRef("member")), IrItem(IrLiteral(","))),
        IrSequence(IrItem(IrLiteral(","))),
        IrSequence(),
    ],
)
def test_sole_ref_is_absent_for_a_quantified_reference_or_another_shape(arm):
    """A repeated reference holds a run, not the rule; two items, a literal and
    an empty arm name no rule either."""
    assert arm.sole_ref() is IrNone


# ── quantifier facts ──────────────────────────────────────────────────────

_QUANTIFIER_FACTS = [
    # (lo, hi, once, optional, unbounded, repeats, fixed, upper)
    (1, 1, True, False, False, False, True, 1),
    (0, 1, False, True, False, False, False, 1),
    (0, IrNone, False, False, True, True, False, None),
    (1, IrNone, False, False, True, True, False, None),
    (2, IrNone, False, False, True, True, False, None),
    (2, 3, False, False, False, True, False, 3),
    (3, 3, False, False, False, True, True, 3),
    (0, 0, False, False, False, False, True, 0),
]


@pytest.mark.parametrize("facts", _QUANTIFIER_FACTS)
def test_a_quantifier_answers_its_own_shape(facts):
    """``1``, ``?``, ``*``, ``+``, ``{2,}``, ``{2,3}``, ``{3}`` and ``{0}``: a
    bounded ``{2,3}`` still repeats, and ``+`` is unbounded although ``lo`` is
    one."""
    lo, hi, *want = facts
    q = IrQuantifier(lo, hi)
    got = [q.once(), q.optional(), q.unbounded(), q.repeats(), q.fixed(), q.upper()]
    assert got == want


def test_the_default_quantifier_is_once():
    """An item built without a quantifier occurs exactly once."""
    assert IrItem(IrRuleRef("x")).quantifier.once()


@pytest.mark.parametrize(
    ("source", "unbounded"),
    [("x*", True), ("x+", True), ("x", False), ("x?", False)],
)
def test_a_parsed_item_reads_its_bound_off_the_quantifier(source, unbounded):
    """Through the standard pipeline: ``x*`` and ``x+`` have no upper bound,
    ``x`` and ``x?`` have one."""
    grammar = parse_grammar(f'root ::= {source}\nx ::= "a"\n', GBNF_FLAVOUR)
    item = tuple(grammar.rules[0].body[0])[0]
    assert item.quantifier.unbounded() is unbounded


def test_unit_literal_is_the_literal_an_item_spells_once():
    """A plain literal item spells its literal."""
    literal = IrItem(IrLiteral("ab")).unit_literal()
    assert isinstance(literal, IrLiteral)
    assert literal == "ab"


@pytest.mark.parametrize(
    "item",
    [
        IrItem(IrLiteral("ab"), IrQuantifier(0, 1)),
        IrItem(IrLiteral("ab"), IrQuantifier(1, IrNone)),
        IrItem(IrRuleRef("ab")),
        IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("b")))),
    ],
)
def test_unit_literal_is_absent_for_a_quantified_literal_or_another_atom(item):
    """``"ab"?`` and ``"ab"+`` spell no fixed text; a reference and a class
    spell no literal at all."""
    assert item.unit_literal() is IrNone


# ── nullability ───────────────────────────────────────────────────────────


def test_nullable_among_finds_an_empty_literal_arm():
    """A rule whose sole arm is the empty literal derives the empty string."""
    rules = [IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral("")))))]
    assert IrRule.nullable_among(rules) == frozenset({"r"})


def test_nullable_among_excludes_a_rule_with_only_non_empty_arms():
    """A rule with no all-nullable arm is not in the result."""
    rules = [IrRule("r", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))]
    assert IrRule.nullable_among(rules) == frozenset()


def test_nullable_among_an_optional_item_makes_its_arm_nullable():
    """A ``lo == 0`` item makes its whole arm nullable even with non-empty text."""
    rules = [
        IrRule(
            "r",
            IrAlternation(IrSequence(IrItem(IrLiteral("x"), IrQuantifier(0, 1)))),
        )
    ]
    assert IrRule.nullable_among(rules) == frozenset({"r"})


def test_nullable_among_propagates_through_a_ruleref_chain():
    """``root`` is nullable because ``mid`` is, transitively — the fixpoint's
    own reason to exist over a one-pass check."""
    rules = [
        IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("mid"))))),
        IrRule("mid", IrAlternation(IrSequence(IrItem(IrLiteral(""))))),
    ]
    assert IrRule.nullable_among(rules) == frozenset({"root", "mid"})


def test_nullable_among_any_arm_nullable_makes_the_whole_alternation_nullable():
    """One nullable arm among several non-nullable ones is enough."""
    rules = [
        IrRule(
            "r",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("x"))),
                IrSequence(IrItem(IrLiteral(""))),
            ),
        )
    ]
    assert IrRule.nullable_among(rules) == frozenset({"r"})


def test_nullable_among_leaves_out_a_cycle_with_no_empty_way_out():
    """``r ::= "a" | s`` / ``s ::= r | "x"``: every derivation ends on ``a`` or
    ``x``, so the least fixpoint never admits either — a walk that answered a
    cycle with "maybe" said both did."""
    rules = [
        IrRule(
            "r",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrRuleRef("s")))
            ),
        ),
        IrRule(
            "s",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("r"))), IrSequence(IrItem(IrLiteral("x")))
            ),
        ),
    ]
    assert IrRule.nullable_among(rules) == frozenset()


def test_nullable_among_never_admits_an_undefined_name():
    """A reference to a rule nothing defines derives nothing at all."""
    rules = [IrRule("r", IrAlternation(IrSequence(IrItem(IrRuleRef("ghost")))))]
    assert IrRule.nullable_among(rules) == frozenset()


def test_ast_nullable_is_its_rules_fixpoint():
    """``IrAst.nullable`` answers over the grammar's own rules."""
    ast = IrAst(
        rules=IrSeq(
            IrRule(
                "root",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("ws")), IrItem(IrLiteral("a")))
                ),
            ),
            IrRule(
                "ws",
                IrAlternation(
                    IrSequence(IrItem(IrLiteral(" "), IrQuantifier(0, IrNone)))
                ),
            ),
        ),
        start=IrStr("root"),
    )
    assert ast.nullable() == frozenset({"ws"})


@pytest.mark.parametrize(
    ("atom", "vanishes"),
    [
        (IrLiteral(""), True),
        (IrLiteral("a"), False),
        (IrCharClass(IrRange(IrChr("a"), IrChr("z"))), False),
        (IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z")))), False),
        (IrAlphabet("gpt2", IrLiteral("<think>")), False),
        (IrRuleRef("n"), True),
        (IrRuleRef("m"), False),
        (IrAlternation(IrSequence(IrItem(IrLiteral("a"))), IrSequence()), True),
        (
            IrAlternation(IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("n")))),
            False,
        ),
    ],
)
def test_each_atom_says_whether_it_vanishes(atom, vanishes):
    """Given which rules derive ε (here only ``n``), each atom answers for itself."""
    assert atom.vanishes(frozenset({"n"})) is vanishes


def test_an_item_that_may_occur_zero_times_vanishes_whatever_its_atom():
    """``lo == 0`` is an empty occurrence; ``lo >= 1`` asks the atom."""
    assert IrItem(IrLiteral("a"), IrQuantifier(0, 1)).vanishes(frozenset())
    assert not IrItem(IrLiteral("a"), IrQuantifier(1, IrNone)).vanishes(frozenset())


def test_an_atom_with_no_answer_refuses():
    """The default raises rather than guessing either way."""

    class _Mute(IrAtom):
        pass

    with pytest.raises(UnsupportedConstructError):
        _Mute().vanishes(frozenset())
