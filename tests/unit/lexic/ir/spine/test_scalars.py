"""Tests for ``lexic.ir.spine.scalars``."""

from __future__ import annotations

import subprocess
import sys

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.spine.records import IrNamedTuple, IrTuple
from lexic.ir.spine.scalars import IrChr, IrInt, IrLeaf, IrScalar, IrStr
from lexic.ir.spine.spine import IrNone


class Rec(IrNamedTuple[IrStr, IrInt]):
    """Local test record: two named fields over positional tuple elements."""

    __slots__ = ()
    a: IrStr
    b: IrInt


def test_bound_explicit_declaration_wins():
    """A class-level ``_bound`` (IrStr/IrTuple) is kept verbatim, not derived."""
    assert IrStr.bound_type() is str
    assert IrTuple.bound_type() is tuple


def test_irscalar_is_a_leaf_and_parents_the_value_leaves():
    """IrScalar is an IrLeaf subclass; IrStr and IrInt both inherit from it."""
    assert issubclass(IrScalar, IrLeaf)
    assert issubclass(IrStr, IrScalar)
    assert issubclass(IrInt, IrScalar)


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


def test_irtuple_construction_and_indexing():
    """IrTuple is constructed variadically; elements are accessible by index."""
    a, b = IrInt(1), IrStr("x")
    t = IrTuple(a, b)
    assert t[0] is a
    assert t[1] is b
    assert len(t) == 2


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


def test_irtuple_is_tuple_subclass():
    """IrTuple instances are native Python tuples (subtype, not wrapper)."""
    t = IrTuple(IrInt(0), IrInt(1))
    assert isinstance(t, tuple)
    assert list(t) == [IrInt(0), IrInt(1)]


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
        setattr(r, "a", IrStr("other"))


def test_irnamedtuple_children_returns_all_elements():
    """IrNamedTuple.children() yields all positional elements in order."""
    a, b = IrStr("p"), IrInt(9)
    r = Rec(a, b)
    assert tuple(r.children()) == (a, b)


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
        "from lexic.ir.spine.scalars import IrStr\n"
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


def test_a_codepoint_past_unicode_refuses_by_name_not_by_chr():
    """Spelling an out-of-range code point is a LEXIC failure, not a builtin one.

    `chr()` raises a bare `ValueError` whose message names neither the value nor
    the grammar it came from, and it reached callers of `parse_grammar` and
    `compile_text` unchanged. STYLE §6: a library failure is a LexicError.
    """
    with pytest.raises(UnsupportedConstructError) as caught:
        str(IrChr(0x110000))
    assert "0x110000" in str(caught.value) or "1114112" in str(caught.value)


def test_the_top_of_the_unicode_range_still_spells():
    """The boundary itself is valid — the refusal starts one past it."""
    assert str(IrChr(0x10FFFF)) == chr(0x10FFFF)
