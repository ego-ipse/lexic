"""IR spine — base classes shared by every IR node (``lexic.ir.base``).

Covers the abstract machinery in isolation, importing only from
``lexic.ir.base``: ``IrSelf`` identity/protocol, the ``IrNone`` sentinel, the
``IrAtom`` marker, ``_bound`` derivation, and the primitive value-leaf bases
(``IrScalar``/``IrStr``/``IrInt``). Where a concrete subclass is needed it is
defined locally — the base module never depends on ``lexic.ir.nodes``.
"""

from __future__ import annotations

from lexic.ir.base import (
    IrAtom,
    IrComposite,
    IrInt,
    IrLeaf,
    IrNode,
    IrNone,
    IrNoneType,
    IrScalar,
    IrSelf,
    IrStr,
    IrTuple,
)

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

    class _Probe[T: IrInt](IrComposite):  # own bounded TypeVar -> derived
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
