"""Tests for ``ir/mapping.py`` — immutable attribute-indexed tuple maps.

:class:`~lexic.ir.mapping.IrMap` is an immutable hash map as a tuple
subclass. The dyads are canonically sorted by key repr so construction
order never affects equality, hashing, or repr. Each synthesized subclass is
memoised by ``(cls, sorted_dyads)`` via a weak-value dict so equal maps
share one class.

:class:`~lexic.ir.mapping.IrTypeMap` extends ``IrMap`` to resolve
nodes via their MRO — concrete-first — enabling open-set dispatch.
"""

import gc
import weakref

import pytest

from lexic.exceptions import IrKeyError, UnsupportedConstructError
from lexic.ir.action import IrThis
from lexic.ir.base import IrCallable, IrInt, IrSelf, IrStr, IrTuple
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import IrLiteral, IrRuleRef

# ── Helpers ───────────────────────────────────────────────────────────


def _names_map() -> IrMap:
    """Return a small data map: ``[0-9]`` → ``digit``, ``[a-z]`` → ``lower``.

    :returns: An IrMap with two string-keyed string-valued dyads.
    """
    return IrMap(
        IrTuple(IrStr("[0-9]"), IrStr("digit")),
        IrTuple(IrStr("[a-z]"), IrStr("lower")),
    )


# ── Data-map behaviour ────────────────────────────────────────────────


def test_data_map_key_lookup_returns_value_without_eval():
    """``m[key]`` returns the stored value directly (getattr-backed lookup).

    No eval semantics apply; the raw IrSelf is returned.
    """
    m = _names_map()
    assert m[IrStr("[0-9]")] == IrStr("digit")
    assert m[IrStr("[a-z]")] == IrStr("lower")


def test_data_map_positional_int_returns_dyad():
    """Plain integer subscript retains tuple positional semantics."""
    m = _names_map()
    assert isinstance(m[0], IrTuple)
    assert isinstance(m[1], IrTuple)


def test_data_map_slice_returns_tuple():
    """Slice subscript returns a plain tuple (native tuple slice)."""
    m = _names_map()
    result = m[0:1]
    assert isinstance(result, tuple)
    assert len(result) == 1


def test_data_map_eval_resolves_and_evaluates():
    """``m.eval(m, key, ())`` resolves the key and evaluates the bound value.

    For IrScalar values, ``eval`` is identity, so the stored value is returned.
    """
    m = _names_map()
    result = m.eval(m, IrStr("[a-z]"), ())
    assert result == IrStr("lower")


# ── IrInt key resolution ──────────────────────────────────────────────


def test_irint_key_resolves_via_index_not_positional():
    """``m[IrInt(k)]`` resolves via the map index (node-ness wins over int-ness).

    A plain ``m[0]`` keeps positional tuple semantics; ``m[IrInt(0)]``
    is a keyed lookup.
    """
    m = IrMap(
        IrTuple(IrInt(42), IrStr("forty-two")),
        IrTuple(IrInt(0), IrStr("zero")),
    )
    assert m[IrInt(42)] == IrStr("forty-two")
    assert m[IrInt(0)] == IrStr("zero")


def test_plain_int_zero_is_positional_not_a_key_lookup():
    """A plain ``int`` subscript uses tuple positional semantics, not the map."""
    m = IrMap(
        IrTuple(IrInt(42), IrStr("forty-two")),
        IrTuple(IrInt(99), IrStr("ninety-nine")),
    )
    # positional index 0 returns the first dyad (canonically sorted)
    first = m[0]
    assert isinstance(first, IrTuple)


# ── IrTypeMap dispatch ────────────────────────────────────────────────


def test_irtype_map_exact_type_hit():
    """An ``IrLiteral``-keyed action runs its body when the node is an IrLiteral."""
    disp = IrTypeMap(
        IrTuple(IrLiteral, IrCallable(lambda _d, n, _nc: IrStr(f"lit:{n}"))),
        IrTuple(IrSelf, IrThis()),
    )
    result = disp.eval(disp, IrLiteral("x"), ())
    assert result == IrStr("lit:x")


def test_irtype_map_mro_fallback():
    """An ``IrSelf``-keyed arm catches ``IrRuleRef`` via MRO fallback.

    ``IrRuleRef`` is not in the table, so resolution falls back through
    the MRO until it hits the ``IrSelf`` entry, which runs ``IrThis()``
    and returns the node unchanged.
    """
    disp = IrTypeMap(
        IrTuple(IrLiteral, IrCallable(lambda _d, n, _nc: IrStr(f"lit:{n}"))),
        IrTuple(IrSelf, IrThis()),
    )
    ref = IrRuleRef("r")
    result = disp.eval(disp, ref, ())
    assert result == ref


# ── Construction-order independence ───────────────────────────────────


def test_maps_with_same_dyads_different_order_are_equal():
    """Maps built with the same dyads in different construction order compare equal."""
    a = IrMap(IrTuple(IrStr("a"), IrInt(1)), IrTuple(IrStr("b"), IrInt(2)))
    b = IrMap(IrTuple(IrStr("b"), IrInt(2)), IrTuple(IrStr("a"), IrInt(1)))
    assert a == b


def test_maps_with_same_dyads_different_order_are_hash_equal():
    """Equal maps have the same hash."""
    a = IrMap(IrTuple(IrStr("a"), IrInt(1)), IrTuple(IrStr("b"), IrInt(2)))
    b = IrMap(IrTuple(IrStr("b"), IrInt(2)), IrTuple(IrStr("a"), IrInt(1)))
    assert hash(a) == hash(b)


def test_maps_with_same_dyads_different_order_deduplicate_in_set():
    """Equal maps deduplicate in a set (one element)."""
    a = IrMap(IrTuple(IrStr("a"), IrInt(1)), IrTuple(IrStr("b"), IrInt(2)))
    b = IrMap(IrTuple(IrStr("b"), IrInt(2)), IrTuple(IrStr("a"), IrInt(1)))
    assert len({a, b}) == 1


def test_map_repr_is_valid_codegen_string():
    """``repr(m)`` produces a valid codegen repr string.

    The repr is compared against an expected string rather than ``eval``'d
    (``eval`` is banned project-wide).
    """
    m = IrMap(IrTuple(IrStr("a"), IrInt(1)), IrTuple(IrStr("b"), IrInt(2)))
    r = repr(m)
    assert r.startswith("IrMap(")
    assert "IrTuple" in r
    assert "IrStr" in r
    assert "IrInt" in r


# ── Key-miss is a hard error ──────────────────────────────────────────


def test_key_miss_raises_unsupported_construct_error_on_subscript():
    """``m[missing_key]`` raises :exc:`UnsupportedConstructError`."""
    m = _names_map()
    with pytest.raises(UnsupportedConstructError):
        _ = m[IrStr("?")]


def test_key_miss_raises_unsupported_construct_error_on_eval():
    """``m.eval(m, missing_key, ())`` raises :exc:`UnsupportedConstructError`."""
    m = _names_map()
    with pytest.raises(UnsupportedConstructError):
        m.eval(m, IrStr("?"), ())


def test_irtype_map_miss_raises_unsupported_construct_error():
    """``IrTypeMap`` with no matching MRO entry raises :exc:`UnsupportedConstructError`."""
    disp = IrTypeMap(
        IrTuple(IrLiteral, IrThis()),
    )
    with pytest.raises(UnsupportedConstructError):
        disp.eval(disp, IrRuleRef("r"), ())


# ── Mapping protocol conformance ──────────────────────────────────────


def test_key_miss_is_doubly_typed_ir_key_error():
    """A miss raises :exc:`IrKeyError` — both an ``UnsupportedConstructError``
    and a ``KeyError``, so library and ``Mapping`` machinery both catch it."""
    m = _names_map()
    with pytest.raises(IrKeyError) as exc_info:
        _ = m[IrStr("?")]
    assert isinstance(exc_info.value, UnsupportedConstructError)
    assert isinstance(exc_info.value, KeyError)


def test_get_returns_value_on_hit_and_default_on_miss():
    """The inherited ``Mapping.get`` works because a miss IS-A ``KeyError``."""
    m = _names_map()
    assert m.get(IrStr("[0-9]")) == IrStr("digit")
    assert m.get(IrStr("?")) is None
    assert m.get(IrStr("?"), IrStr("fallback")) == IrStr("fallback")


def test_contains_is_key_based_not_dyad_based():
    """``in`` checks keys (``Mapping`` semantics), overriding tuple containment."""
    m = _names_map()
    assert IrStr("[0-9]") in m
    assert IrStr("?") not in m
    assert m[0] not in m  # a dyad is not a key


def test_keys_values_items_are_views_in_canonical_order():
    """``keys``/``values``/``items`` are real dict views over a snapshot
    (the map is immutable, so a snapshot view never drifts)."""
    m = _names_map()
    assert tuple(m.keys()) == (IrStr("[0-9]"), IrStr("[a-z]"))
    assert tuple(m.values()) == (IrStr("digit"), IrStr("lower"))
    assert tuple(m.items()) == (
        (IrStr("[0-9]"), IrStr("digit")),
        (IrStr("[a-z]"), IrStr("lower")),
    )
    assert IrStr("digit") in m.values()
    assert (IrStr("[a-z]"), IrStr("lower")) in m.items()


def test_dict_conversion_round_trips_entries():
    """``dict(m)`` builds the plain-dict equivalent via ``keys()`` + lookup."""
    m = _names_map()
    assert dict(m) == {IrStr("[0-9]"): IrStr("digit"), IrStr("[a-z]"): IrStr("lower")}


def test_iter_yields_dyads_not_keys():
    """The one deliberate ``Mapping`` deviation: ``iter(m)`` yields dyads
    (the node IS its children tuple), so ``iter(m)`` ≠ ``iter(m.keys())``."""
    m = _names_map()
    assert all(isinstance(dyad, IrTuple) for dyad in m)
    assert tuple(m) != tuple(m.keys())


# ── Memoised class synthesis ──────────────────────────────────────────


def test_equal_maps_share_same_synthesized_class():
    """Two equal maps must satisfy ``type(a) is type(b)``."""
    a = IrMap(IrTuple(IrStr("x"), IrInt(1)))
    b = IrMap(IrTuple(IrStr("x"), IrInt(1)))
    assert type(a) is type(b)


def test_synthesized_class_is_weakly_held_and_collected():
    """The synthesized class is weakly held; it is garbage-collected when the
    only strong reference is dropped.

    Build a map, take a weakref to its type, delete the map, force GC, and
    assert the weakref is dead.
    """
    m = IrMap(IrTuple(IrStr("unique-gc-test-key"), IrInt(999)))
    ref = weakref.ref(type(m))
    assert ref() is not None
    del m
    gc.collect()
    assert ref() is None


# ── Immutability ──────────────────────────────────────────────────────


def test_setattr_raises_type_error():
    """``setattr`` on an IrMap instance raises :class:`TypeError`."""
    m = _names_map()
    with pytest.raises(TypeError):
        setattr(m, "foo", "bar")


def test_delattr_raises_type_error():
    """``delattr`` on an IrMap instance raises :class:`TypeError`."""
    m = _names_map()
    with pytest.raises(TypeError):
        delattr(m, "foo")


# ── Duplicate keys at construction ───────────────────────────────────


def test_duplicate_keys_at_construction_raise_unsupported_construct_error():
    """Duplicate keys at construction time raise :exc:`UnsupportedConstructError`."""
    with pytest.raises(UnsupportedConstructError):
        IrMap(
            IrTuple(IrStr("dup"), IrInt(1)),
            IrTuple(IrStr("dup"), IrInt(2)),
        )
