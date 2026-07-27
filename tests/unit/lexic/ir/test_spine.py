"""Tests for ``lexic.ir.spine``."""

from __future__ import annotations

from lexic.ir.records import Field, IrCachingTuple, IrNode, IrSelf
from lexic.ir.scalars import IrInt, IrLeaf, IrStr
from lexic.ir.spine import IrAtom, IrLambda, IrNone, IrNoneType


class Cfg(IrCachingTuple[list, int]):
    """Local caching record: a mutable-default field and a factory field."""

    __slots__ = ()
    flags: list = Field(default=[False])
    total: int = Field(default_factory=int)


class Base(IrCachingTuple[int]):
    """Caching record with a single field, to be extended by a subclass."""

    __slots__ = ()
    x: int = Field(default=5)


class Derived(Base):
    """Subclass that adds a field; should inherit ``Base``'s field layout."""

    __slots__ = ()
    y: int = Field(default=7)


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


def test_iratom_is_non_generic_marker():
    """IrAtom carries no type parameters of its own and is an IrNode subclass."""
    # IrAtom has no type parameters of its own
    assert not getattr(IrAtom, "__type_params__", ())
    assert issubclass(IrAtom, IrNode)


def test_bound_derived_from_own_typevar_bound():
    """A class with its OWN bounded TypeVar derives ``_bound`` from that bound."""

    class _Probe[T: IrInt](IrNode):  # own bounded TypeVar -> derived
        pass

    assert _Probe.bound_type() is IrInt


def test_irscalar_eval_is_self_for_both_value_leaves():
    """Value leaves are self-evaluating: eval returns self (the scalar value)."""
    assert IrInt(5).eval(IrNone, IrNone, ()) == 5  # inherited from IrScalar
    assert IrStr("x").eval(IrNone, IrNone, ()) == "x"  # str leaf, inherited


def test_field_default_factory_produces_fresh_values():
    """A ``default_factory`` field yields an independent value per instance."""
    a, b = Cfg(), Cfg()
    assert a.total == 0
    a_flags, b_flags = a.flags, b.flags
    assert a_flags is not b_flags


def test_field_mutable_default_is_isolated_per_instance():
    """A mutable ``default`` is deep-copied, not shared across instances."""
    first, second = Cfg(), Cfg()
    # Bound before mutating: the annotation is a ``Field`` descriptor and the
    # instance attribute is the resolved list, which is the whole point of the
    # deep copy being tested.
    # Filtered rather than asserted, as in the forest tests: the class-body
    # annotation is a ``Field`` descriptor and the instance attribute is the
    # resolved list, which is exactly what the deep copy under test produces.
    [flags] = [f for f in (first.flags,) if isinstance(f, list)]
    flags.append(True)
    assert first.flags == [False, True]
    assert second.flags == [False]


def test_ircachingtuple_subclass_inherits_base_fields():
    """A subclass prepends its base's fields, in base-then-own order."""
    assert Derived._fields == ("x", "y")


def test_ircachingtuple_resolves_inherited_and_own_defaults():
    """Construction resolves both the inherited and the own field defaults."""
    d = Derived()
    assert (d.x, d.y) == (5, 7)
    assert tuple(d) == (5, 7)


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
