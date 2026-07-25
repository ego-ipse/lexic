"""IR spine — base classes shared by every IR node (``lexic.ir.base``).

Covers the abstract machinery: ``IrSelf`` identity/protocol, the ``IrNone``
sentinel, the ``IrAtom`` marker, ``_bound`` derivation, the primitive
value-leaf bases (``IrScalar``/``IrStr``/``IrInt``), and the tuple tier
(``IrTuple``/``IrSeq``/``IrNamedTuple``). Where a concrete subclass is needed
it is defined locally.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrArgs, IrJoin
from lexic.ir.base import (
    Field,
    IrAtom,
    IrCachingTuple,
    IrChr,
    IrInt,
    IrLambda,
    IrLeaf,
    IrNamedTuple,
    IrNode,
    IrNone,
    IrNoneType,
    IrScalar,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
)
from lexic.ir.nodes import IrAlternation, IrItem, IrLiteral, IrQuantifier, IrSequence

# ── IrSelf / IrNone / IrAtom contract ─────────────────────────────────


def test_irself_identity_call_returns_self():
    """IrSelf.__call__ is identity: returns self regardless of d/n/nc args."""

    class L(IrLeaf):
        """Minimal IrLeaf subclass for testing identity call."""

        __slots__ = ()

        def __repr__(self) -> str:
            """Return a fixed repr string."""
            return "L()"

    leaf = L()
    assert leaf(IrNone, IrNone, ()) is leaf


def test_irnone_is_final_singleton_and_is_irself():
    """IrNone is a singleton: all constructions return the same instance."""
    assert IrNone is IrNoneType()  # public value IS the singleton instance
    assert isinstance(IrNone, (IrSelf, IrNoneType))
    # @final is a STATIC-only guarantee (pyright flags subclassing); no runtime raise.


def test_iratom_is_non_generic_marker():
    """IrAtom carries no type parameters of its own and is an IrNode subclass."""
    # IrAtom has no type parameters of its own
    assert not getattr(IrAtom, "__type_params__", ())
    assert issubclass(IrAtom, IrNode)


# ── _bound derivation (own __type_params__ only; explicit wins; never MRO) ──


def test_bound_explicit_declaration_wins():
    """A class-level ``_bound`` (IrStr/IrTuple) is kept verbatim, not derived."""
    assert IrStr.bound_type() is str
    assert IrTuple.bound_type() is tuple


def test_bound_derived_from_own_typevar_bound():
    """A class with its OWN bounded TypeVar derives ``_bound`` from that bound."""

    class _Probe[T: IrInt](IrNode):  # own bounded TypeVar -> derived
        pass

    assert _Probe.bound_type() is IrInt


# ── IrScalar / IrStr / IrInt ──────────────────────────────────────────


def test_irscalar_is_a_leaf_and_parents_the_value_leaves():
    """IrScalar is an IrLeaf subclass; IrStr and IrInt both inherit from it."""
    assert issubclass(IrScalar, IrLeaf)
    assert issubclass(IrStr, IrScalar)
    assert issubclass(IrInt, IrScalar)


def test_irscalar_eval_is_self_for_both_value_leaves():
    """Value leaves are self-evaluating: eval returns self (the scalar value)."""
    assert IrInt(5).eval(IrNone, IrNone, ()) == 5  # inherited from IrScalar
    assert IrStr("x").eval(IrNone, IrNone, ()) == "x"  # str leaf, inherited


def test_irint_is_int_and_scalar():
    """IrInt is simultaneously an int and an IrScalar — no wrapper boxing."""
    assert isinstance(IrInt(5), int)
    assert isinstance(IrInt(5), IrScalar)
    assert IrInt(5) == 5  # native int equality
    assert IrInt(5) + 1 == 6  # native int arithmetic


def test_irint_default_is_zero():
    """IrInt() with no argument defaults to 0, matching int() behaviour."""
    assert IrInt() == 0


def test_irint_bound_is_int():
    """IrInt._bound resolves to int (explicit ClassVar, parallel to IrStr._bound = str)."""
    assert IrInt.bound_type() is int


def test_irint_repr_is_codegen():
    """repr(IrInt(5)) produces the constructor call 'IrInt(5)' (repr-is-codegen)."""
    assert repr(IrInt(5)) == "IrInt(5)"


def test_irscalar_eq_hash_delegate_to_primitive():
    """IrScalar.__eq__/__hash__ reach str/int (not object identity) via super().

    Regression guard: if a future refactor inserts an __eq__/__hash__ between
    IrScalar and str/int in the MRO — or breaks the super() delegation — these
    fall back to object identity and silently break value equality and keying.
    """
    assert IrStr("x") == "x"  # str.__eq__, not object identity
    assert IrInt(5) == 5  # int.__eq__, not object identity
    assert hash(IrStr("x")) == hash("x")  # str.__hash__
    assert hash(IrInt(5)) == hash(5)  # int.__hash__
    by_primitive: dict[str, int] = {IrStr("x"): 1}  # leaf keys by primitive value
    assert by_primitive["x"] == 1


def test_irscalar_eq_is_type_aware_across_tiers():
    """Distinct value-leaf kinds never compare equal, even with matching payload."""
    assert IrInt(5) != IrStr("5")  # int leaf vs str leaf — distinct IrScalar kinds
    assert IrStr("5") != IrInt(5)  # symmetric

    class _OtherStr(IrStr):  # a second str-leaf kind
        __slots__ = ()

    assert IrStr("x") != _OtherStr("x")  # same payload, distinct kinds
    assert len({IrStr("a"), IrStr("a"), _OtherStr("a")}) == 2


# ── IrTuple ───────────────────────────────────────────────────────────


def test_irtuple_construction_and_indexing():
    """IrTuple is constructed variadically; elements are accessible by index."""
    a, b = IrInt(1), IrStr("x")
    t = IrTuple(a, b)
    assert t[0] is a
    assert t[1] is b
    assert len(t) == 2


def test_irtuple_children_returns_elements():
    """IrTuple.children() returns self as an IrSelf sequence (elements in order)."""
    a, b = IrInt(3), IrStr("y")
    t = IrTuple(a, b)
    assert tuple(t.children()) == (a, b)


def test_irtuple_rebuild_produces_same_type():
    """IrTuple.rebuild(new_children) constructs a new instance of the same type."""
    a, b, c = IrInt(1), IrInt(2), IrInt(3)
    t = IrTuple(a, b)
    rebuilt = t.rebuild((b, c))
    assert type(rebuilt) is type(t)
    assert rebuilt[0] is b
    assert rebuilt[1] is c


def test_irtuple_repr_is_codegen():
    """repr(IrTuple(...)) reproduces the constructor call."""
    t = IrTuple(IrStr("a"), IrInt(7))
    assert repr(t) == "IrTuple(IrStr('a'), IrInt(7))"


def test_record_repr_elision_is_type_strict():
    """A default-equal value of the WRONG type is never elided (F-REPR-1).

    Empty records compare equal cross-class under tuple equality
    (``IrArgs() == IrTuple()``), so an equality-only elision would render
    ``IrJoin(IrArgs())`` as ``IrJoin()`` and reconstruct it with the wrong
    default ``IrTuple()`` — repr-stable but behaviorally different (the
    GBNF ``literal`` reduction would join nothing). The elision requires
    the same concrete type as the declared default.
    """
    joined_args = IrJoin(IrArgs())
    assert repr(joined_args) == "IrJoin(IrArgs())"
    # same-type defaults still elide (the IrItem precedent stays)
    assert repr(IrItem(IrLiteral("a"), IrQuantifier(1, 1))) == (
        "IrItem(IrLiteral('a'))"
    )
    # and a genuinely-default empty IrTuple still elides
    assert repr(IrJoin(IrTuple())) == "IrJoin()"


def test_irtuple_eval_rebuilds_with_evaluated_elements():
    """IrTuple.eval walks each element via eval and rebuilds the tuple."""
    a, b = IrInt(1), IrStr("z")
    t = IrTuple(a, b)
    result = t.eval(IrNone, IrNone, ())
    # self-evaluating leaves → same values, fresh tuple
    assert result == t
    assert isinstance(result, IrTuple)


def test_irtuple_is_tuple_subclass():
    """IrTuple instances are native Python tuples (subtype, not wrapper)."""
    t = IrTuple(IrInt(0), IrInt(1))
    assert isinstance(t, tuple)
    assert list(t) == [IrInt(0), IrInt(1)]


def test_irtuple_empty_construction():
    """IrTuple() with no arguments produces an empty tuple node."""
    t = IrTuple()
    assert len(t) == 0
    assert not tuple(t.children())


# ── IrSeq ─────────────────────────────────────────────────────────────


def test_irseq_is_irtuple_subclass():
    """IrSeq is a subclass of IrTuple (and thus of tuple)."""
    assert issubclass(IrSeq, IrTuple)
    assert issubclass(IrSeq, tuple)


def test_irseq_bound_type_is_tuple():
    """IrSeq._bound is tuple — inherited from IrTuple, not re-derived from T."""
    assert IrSeq.bound_type() is tuple


def test_irseq_concrete_subclasses_are_irseq():
    """IrSequence and IrAlternation are IrSeq subclasses."""
    assert issubclass(IrSequence, IrSeq)
    assert issubclass(IrAlternation, IrSeq)


# ── IrNamedTuple ──────────────────────────────────────────────────────


class Rec(IrNamedTuple[IrStr, IrInt]):
    """Local test record: two named fields over positional tuple elements."""

    __slots__ = ()
    a: IrStr
    b: IrInt


def test_irnamedtuple_named_access_equals_positional():
    """Named field accessors read the same element as positional indexing."""
    r = Rec(IrStr("hello"), IrInt(42))
    assert r.a is r[0]
    assert r.b is r[1]


def test_irnamedtuple_construction_is_positional():
    """Rec is constructed positionally (inherited IrTuple.__new__)."""
    r = Rec(IrStr("x"), IrInt(3))
    assert len(r) == 2
    assert r[0] == "x"
    assert r[1] == 3


def test_irnamedtuple_is_a_tuple():
    """IrNamedTuple instances are native Python tuples."""
    r = Rec(IrStr("t"), IrInt(0))
    assert isinstance(r, tuple)


def test_irnamedtuple_is_immutable():
    """Assigning to a named field raises AttributeError (tuples are immutable)."""
    r = Rec(IrStr("v"), IrInt(1))
    with pytest.raises(AttributeError):
        r.a = IrStr("other")  # type: ignore[misc]


def test_irnamedtuple_children_returns_all_elements():
    """IrNamedTuple.children() yields all positional elements in order."""
    a, b = IrStr("p"), IrInt(9)
    r = Rec(a, b)
    assert tuple(r.children()) == (a, b)


# ── Field / IrCachingTuple ────────────────────────────────────────────


class Cfg(IrCachingTuple[list, int]):
    """Local caching record: a mutable-default field and a factory field."""

    __slots__ = ()
    flags: list = Field(default=[False])
    total: int = Field(default_factory=int)


def test_field_requires_a_default_or_factory():
    """``Field()`` with neither (nor both) argument raises at construction."""
    with pytest.raises(TypeError):
        Field()  # type: ignore[call-overload]  # intentional misuse under test


def test_field_default_factory_produces_fresh_values():
    """A ``default_factory`` field yields an independent value per instance."""
    a, b = Cfg(), Cfg()
    assert a.total == 0
    a_flags, b_flags = a.flags, b.flags
    assert a_flags is not b_flags


def test_field_mutable_default_is_isolated_per_instance():
    """A mutable ``default`` is deep-copied, not shared across instances."""
    first = Cfg()
    first.flags.append(True)
    second = Cfg()
    assert first.flags == [False, True]
    assert second.flags == [False]


class Base(IrCachingTuple[int]):
    """Caching record with a single field, to be extended by a subclass."""

    __slots__ = ()
    x: int = Field(default=5)


class Derived(Base):
    """Subclass that adds a field; should inherit ``Base``'s field layout."""

    __slots__ = ()
    y: int = Field(default=7)


def test_ircachingtuple_subclass_inherits_base_fields():
    """A subclass prepends its base's fields, in base-then-own order."""
    assert Derived._fields == ("x", "y")


def test_ircachingtuple_resolves_inherited_and_own_defaults():
    """Construction resolves both the inherited and the own field defaults."""
    d = Derived()
    assert (d.x, d.y) == (5, 7)
    assert tuple(d) == (5, 7)


class LeftMixin(IrCachingTuple[int]):
    """One field-bearing caching base for the multiple-inheritance case."""

    __slots__ = ()
    a: int = Field(default=1)


class RightMixin(IrCachingTuple[int]):
    """A second, independent field-bearing caching base."""

    __slots__ = ()
    b: int = Field(default=2)


class Diamond(LeftMixin, RightMixin):
    """Combines two caching bases plus an own field."""

    __slots__ = ()
    c: int = Field(default=3)


def test_ircachingtuple_merges_all_bases_under_multiple_inheritance():
    """Fields from every caching base are merged (reverse-MRO order), then own."""
    assert Diamond._fields == ("b", "a", "c")  # reverse-MRO: RightMixin, LeftMixin
    d = Diamond()
    assert (d.a, d.b, d.c) == (1, 2, 3)
    assert tuple(d) == (2, 1, 3)


# ── IrLambda ──────────────────────────────────────────────────────────


def test_irlambda_closure_is_eval():
    """IrLambda stores the closure as eval — the closure IS the eval slot."""

    def constant(_d, _n, _nc):
        return IrStr("result")

    lam = IrLambda(constant)
    result = lam.eval(IrNone, IrNone, ())
    assert result == IrStr("result")


def test_irlambda_eval_receives_full_protocol_args():
    """IrLambda.eval forwards d, n, nc to the closure."""
    received: list[object] = []

    def capture(d, n, nc):
        received.extend([d, n, nc])
        return IrStr("ok")

    d_sentinel = IrNone
    n_sentinel = IrStr("n")
    nc_arg = (IrStr("c"),)
    IrLambda(capture).eval(d_sentinel, n_sentinel, nc_arg)
    assert received[0] is d_sentinel
    assert received[1] is n_sentinel
    assert received[2] is nc_arg


def test_irlambda_named_function_repr():
    """IrLambda wrapping a named function renders ``IrLambda(<name>)``."""

    def my_fn(_d, _n, _nc):
        return IrNone

    assert repr(IrLambda(my_fn)) == "IrLambda(my_fn)"


def test_irlambda_equality_is_by_identity():
    """Two IrLambda wrapping distinct closures are not equal."""

    def noop(_d, _n, _nc):
        return IrNone

    a = IrLambda(noop)
    b = IrLambda(noop)
    # equality is identity: two separate IrLambda objects are not equal
    assert a is not b


def test_irlambda_is_irnode():
    """IrLambda is an IrNode — it participates in the IR hierarchy."""

    def noop(_d, _n, _nc):
        return IrNone

    assert isinstance(IrLambda(noop), IrNode)


# ── IrChr ─────────────────────────────────────────────────────────────


def test_irchr_from_glyph_and_int_are_equal():
    """IrChr("A") == IrChr(0x41)"""
    assert IrChr("A") == IrChr(0x41)


def test_irchr_str_is_glyph_and_repr_is_codegen():
    """IrChr.str() is the glyph, repr() is the constructor call."""
    assert str(IrChr(0x41)) == "A"
    assert repr(IrChr(0x41)) == "IrChr(65)"


def test_irchr_is_leaf_kind_distinct_from_irint():
    """IrChr is a leaf kind distinct from IrInt."""
    assert IrChr(0x41) != IrInt(0x41)  # distinct leaf kinds never compare equal
    assert IrChr(0x41) == 0x41  # but a leaf still matches its plain int


def test_irchr_eval_returns_glyph_irstr():
    """IrChr.eval returns an IrStr with the glyph."""
    assert IrChr(0x41).eval(IrNone, IrNone, ()) == IrStr("A")


def test_irchr_multichar_glyph_raises():
    """IrChr raises on multi-char glyphs"""
    with pytest.raises(UnsupportedConstructError):
        IrChr("AB")


# --- IrSelf.ensure — the boundary narrow -----------------------------------


def test_ensure_returns_the_value_when_it_is_an_instance():
    """A matching value passes through unchanged — identity, not a copy."""
    node = IrStr("x")
    assert IrStr.ensure(node) is node


def test_ensure_accepts_a_subclass():
    """Narrowing is isinstance, so a subclass satisfies its base."""
    node = IrChr(0x41)
    assert IrScalar.ensure(node) is node


def test_ensure_refuses_a_wrong_type_naming_both():
    """The message names what arrived and what was wanted."""
    with pytest.raises(UnsupportedConstructError, match="IrStr, not IrInt"):
        IrInt.ensure(IrStr("x"))


def test_ensure_refuses_a_non_ir_value():
    """It narrows any object, not only IR nodes — the boundary takes anything."""
    with pytest.raises(UnsupportedConstructError, match="int, not IrStr"):
        IrStr.ensure(3)


def test_ensure_context_is_woven_into_the_message():
    """``what`` names the subject so a caller's error says which field failed."""
    with pytest.raises(UnsupportedConstructError, match="the document is int"):
        IrStr.ensure(3, "the document")


def test_ensure_is_a_check_not_an_assert():
    """It raises under ``-O``, where an ``assert isinstance`` would vanish.

    This is why the narrow is a call rather than an assert: the examples and
    the boundary seams must fail the same way in optimized mode.
    """
    probe = (
        "from lexic.ir.base import IrStr\n"
        "from lexic.exceptions import UnsupportedConstructError\n"
        "try:\n"
        "    IrStr.ensure(3)\n"
        "except UnsupportedConstructError:\n"
        "    print('raised')\n"
    )
    out = subprocess.run(
        [sys.executable, "-O", "-c", probe], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "raised"
