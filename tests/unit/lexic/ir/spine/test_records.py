"""Tests for ``lexic.ir.spine.records``."""

from __future__ import annotations

import pytest

from lexic.ir.action.access import IrArgs
from lexic.ir.action.compute import IrJoin
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrSequence,
)
from lexic.ir.spine.records import Field, IrCachingTuple, IrSeq, IrTuple
from lexic.ir.spine.scalars import IrInt, IrStr
from lexic.ir.spine.spine import IrNone


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


def test_irtuple_children_returns_elements():
    """IrTuple.children() returns self as an IrSelf sequence (elements in order)."""
    a, b = IrInt(3), IrStr("y")
    t = IrTuple(a, b)
    assert tuple(t.children()) == (a, b)


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


def test_irtuple_empty_construction():
    """IrTuple() with no arguments produces an empty tuple node."""
    t = IrTuple()
    assert len(t) == 0
    assert not tuple(t.children())


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


def test_field_requires_a_default_or_factory():
    """``Field()`` with neither (nor both) argument raises at construction."""
    with pytest.raises(TypeError):
        Field()  # type: ignore[call-overload]  # intentional misuse under test


def test_ircachingtuple_merges_all_bases_under_multiple_inheritance():
    """Fields from every caching base are merged (reverse-MRO order), then own."""
    assert Diamond._fields == ("b", "a", "c")  # reverse-MRO: RightMixin, LeftMixin
    d = Diamond()
    assert (d.a, d.b, d.c) == (1, 2, 3)
    assert tuple(d) == (2, 1, 3)
