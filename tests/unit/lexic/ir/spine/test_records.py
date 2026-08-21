"""Tests for ``lexic.ir.spine.records``."""

from __future__ import annotations

import types
from typing import ClassVar

import pytest

from lexic.ir.action.access import IrArgs
from lexic.ir.action.flow.compute import IrJoin
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrSequence,
)
from lexic.ir.spine.records import (
    Field,
    IrCachingTuple,
    IrNamedTuple,
    IrSeq,
    IrTuple,
)
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


# ── PEP 649: fields must register without `from __future__ import annotations` ──


def _lazily_annotated(name: str, fields: dict[str, object], **body: object) -> type:
    """A record class shaped the way Python 3.14 compiles an annotated body.

    Under PEP 649 a class body carrying annotations compiles to an
    ``__annotate_func__`` and NO ``__annotations__`` entry — the mapping is
    computed on access. ``from __future__ import annotations`` opts out of
    that and stores a plain dict eagerly, which is why every module in
    ``src/lexic`` (all of which carry the import) never exposed the defect.

    This builds the lazy shape directly, so the case is testable from a module
    that does carry the future import.
    """

    def fill(namespace: dict[str, object]) -> None:
        namespace["__annotate_func__"] = lambda _format: dict(fields)
        namespace.update(body)

    return types.new_class(name, (IrNamedTuple[IrStr, IrStr],), {}, fill)


def test_a_lazily_annotated_body_has_no_dunder_annotations_in_its_dict():
    """The precondition: a ``__dict__`` read finds nothing to register.

    Pinned so the test below cannot pass for the wrong reason — if this stops
    being true, the field test is no longer exercising PEP 649 at all.
    """
    made = _lazily_annotated("Precondition", {"a": IrStr})
    assert "__annotations__" not in made.__dict__
    assert "__annotate_func__" in made.__dict__


def test_fields_register_for_a_lazily_annotated_record():
    """Fields come from the annotation API, not from ``cls.__dict__``.

    Reading ``cls.__dict__["__annotations__"]`` yields ``{}`` for this class
    (pinned above), so before the fix ``_fields`` was ``()``: every attribute
    raised ``AttributeError``, defaults never applied, and the record silently
    degraded to a bare tuple that still constructed and still compared.
    """
    made = _lazily_annotated("Lazy", {"a": IrStr, "b": IrStr}, b=IrStr("B"))
    assert made._fields == ("a", "b")
    built = made(IrStr("x"))
    assert built.a == IrStr("x")
    assert built.b == IrStr("B")  # the default applied
    assert tuple(built) == (IrStr("x"), IrStr("B"))


def test_classvars_are_excluded_for_a_lazily_annotated_record():
    """A ``ClassVar`` is class data, not a field, on the lazy path too."""
    made = _lazily_annotated(
        "LazyClassVar",
        {"_child_attrs": ClassVar[tuple[str, ...]], "a": IrStr},
        _child_attrs=(),
    )
    assert made._fields == ("a",)


# ── surplus positional values are refused, never silently stored ──


def test_more_positional_values_than_fields_raises():
    """The surplus would land in the tuple unnamed, reachable by no accessor."""

    class TwoFields(IrNamedTuple[IrStr, IrStr]):
        """Two fields."""

        a: IrStr
        b: IrStr = IrStr("B")

    surplus: list[IrStr] = [IrStr("1"), IrStr("2"), IrStr("3")]
    with pytest.raises(TypeError, match="takes 2 positional field"):
        TwoFields(*surplus)


def test_a_surplus_positional_does_not_become_an_unnamed_element():
    """The record's length never exceeds its own field count."""

    class OneField(IrNamedTuple[IrStr]):
        """One field."""

        a: IrStr

    assert len(OneField(IrStr("1"))) == len(OneField._fields) == 1
    surplus: list[IrStr] = [IrStr("1"), IrStr("2")]
    with pytest.raises(TypeError):
        OneField(*surplus)


def test_a_subclass_declaring_no_fields_keeps_its_parents():
    """``type("Mine", (Rec,), {})`` IS a ``Rec`` and has ``Rec``'s fields.

    Overwriting ``_fields`` with the subclass's own (empty) annotations made
    such a subclass a fieldless record: its values landed in the tuple unnamed,
    every accessor was gone, and ``repr`` showed nothing while ``len`` showed
    the elements. Surfaced by the surplus-positional check, which fired on a
    record that had silently lost the fields its arguments were for.
    """

    class Rec(IrNamedTuple[IrStr, IrStr]):
        """Two fields, one with a default."""

        a: IrStr
        b: IrStr = IrStr("B")

    sub = type("Sub", (Rec,), {})
    assert sub._fields == ("a", "b")
    built = sub(IrStr("x"))
    assert (built.a, built.b) == (IrStr("x"), IrStr("B"))
    assert len(built) == 2


def test_a_subclass_that_adds_fields_still_replaces_the_shape():
    """Declaring fields is still an own-shape declaration, not a merge.

    ``IrCachingTuple`` is the tier that merges bases; plain ``IrNamedTuple``
    takes the declaring class's fields as written. Pinned so the inheritance
    rule above is not mistaken for merging.
    """

    class Base(IrNamedTuple[IrStr]):
        """One field."""

        a: IrStr

    class Narrower(Base):
        """Declares its own field, so it declares its own shape."""

        b: IrStr

    assert Narrower._fields == ("b",)
