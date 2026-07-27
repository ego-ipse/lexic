"""Tests for ``ir/mapping.py`` — the common-ancestor fast map family.

Covers the behavioural contract of :mod:`~lexic.ir.mapping` (key lookup,
``IR_DEFAULT`` fallback, ``IrTypeMap`` MRO dispatch, immutability, structural
equality) without positional int/slice indexing or per-table synthesized classes.
The two concrete maps are siblings under :class:`~lexic.ir.mapping.IrMapping`;
:class:`~lexic.ir.mapping.IrMultiMap` reads return the **live** bucket (no
snapshot copy).
"""

import pytest

from lexic.exceptions import IrKeyError, UnsupportedConstructError
from lexic.ir.control import IrThis
from lexic.ir.mapping import IR_DEFAULT, IrMap, IrMapping, IrMultiMap, IrTypeMap
from lexic.ir.nodes import IrLiteral, IrRuleRef
from lexic.ir.records import IrTuple
from lexic.ir.scalars import IrInt, IrStr
from lexic.ir.spine import IrLambda, IrNone, IrSelf

# ── Helpers ───────────────────────────────────────────────────────────


def names_map() -> IrMap:
    """A small data map: ``[0-9]`` → ``digit``, ``[a-z]`` → ``lower``.

    :returns: An IrMap with two string-keyed string-valued dyads.
    """
    return IrMap(
        IrTuple(IrStr("[0-9]"), IrStr("digit")),
        IrTuple(IrStr("[a-z]"), IrStr("lower")),
    )


def default_map() -> IrMap:
    """A map with one exact key and a catch-all :data:`IR_DEFAULT` entry.

    :returns: IrMap with ``IrStr("a") → IrStr("hitA")`` and default ``IrStr("DEFAULT")``.
    """
    return IrMap(
        IrTuple(IrStr("a"), IrStr("hitA")),
        IrTuple(IR_DEFAULT, IrStr("DEFAULT")),
    )


# ── Common ancestor ───────────────────────────────────────────────────


def test_both_maps_share_the_ancestor():
    """``IrMap`` and ``IrMultiMap`` are both :class:`IrMapping`."""
    assert isinstance(names_map(), IrMapping)
    assert isinstance(IrMultiMap(), IrMapping)


# ── IrMap behaviour ───────────────────────────────────────────────────


def test_key_lookup_returns_value():
    """``m[key]`` returns the stored value directly."""
    m = names_map()
    assert m[IrStr("[0-9]")] == IrStr("digit")
    assert m[IrStr("[a-z]")] == IrStr("lower")


def test_eval_resolves_and_evaluates():
    """``m.eval(m, key, ())`` resolves the key and evaluates the bound value."""
    assert names_map().eval(names_map(), IrStr("[a-z]"), ()) == IrStr("lower")


def test_irint_key_resolves_via_index():
    """``m[IrInt(k)]`` resolves via the index (node keys, not positional)."""
    m = IrMap(
        IrTuple(IrInt(42), IrStr("forty-two")),
        IrTuple(IrInt(0), IrStr("zero")),
    )
    assert m[IrInt(42)] == IrStr("forty-two")
    assert m[IrInt(0)] == IrStr("zero")


def test_get_returns_value_on_hit_and_default_on_miss():
    """``get`` returns the value on a hit and the default on a miss."""
    m = names_map()
    assert m.get(IrStr("[0-9]")) == IrStr("digit")
    assert m.get(IrStr("?")) is None
    assert m.get(IrStr("?"), IrStr("fallback")) == IrStr("fallback")


def test_contains_is_key_based():
    """``in`` checks keys, not dyads."""
    m = names_map()
    assert IrStr("[0-9]") in m
    assert IrStr("?") not in m


def test_keys_values_items_canonical_order():
    """``keys``/``values``/``items`` are views in canonical (sorted) order."""
    m = names_map()
    assert tuple(m.keys()) == (IrStr("[0-9]"), IrStr("[a-z]"))
    assert tuple(m.values()) == (IrStr("digit"), IrStr("lower"))
    assert tuple(m.items()) == (
        (IrStr("[0-9]"), IrStr("digit")),
        (IrStr("[a-z]"), IrStr("lower")),
    )
    assert IrStr("digit") in m.values()
    assert (IrStr("[a-z]"), IrStr("lower")) in m.items()


def test_iter_yields_dyads_not_keys():
    """``iter(m)`` yields dyads (the walk contract), not keys."""
    m = names_map()
    assert all(isinstance(dyad, IrTuple) for dyad in m)
    assert tuple(m) != tuple(m.keys())


def test_len_counts_entries():
    """``len(m)`` is the number of entries."""
    assert len(names_map()) == 2


def test_dict_conversion_round_trips_entries():
    """``dict(m.items())`` builds the plain-dict equivalent."""
    m = names_map()
    assert dict(m.items()) == {
        IrStr("[0-9]"): IrStr("digit"),
        IrStr("[a-z]"): IrStr("lower"),
    }


# ── Structural equality / construction order ──────────────────────────


def test_same_dyads_different_order_are_equal_and_hash_equal():
    """Same dyads in different order compare equal and hash equal and dedup."""
    a = IrMap(IrTuple(IrStr("a"), IrInt(1)), IrTuple(IrStr("b"), IrInt(2)))
    b = IrMap(IrTuple(IrStr("b"), IrInt(2)), IrTuple(IrStr("a"), IrInt(1)))
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_distinct_maps_are_unequal():
    """Maps with different entries are not equal."""
    assert IrMap(IrTuple(IrStr("a"), IrInt(1))) != IrMap(IrTuple(IrStr("a"), IrInt(2)))


def test_equal_maps_share_concrete_type():
    """Two equal maps have the same concrete type (both are ``IrMap``)."""
    a = IrMap(IrTuple(IrStr("x"), IrInt(1)))
    b = IrMap(IrTuple(IrStr("x"), IrInt(1)))
    assert type(a) is type(b)


def test_map_repr_is_codegen_string():
    """``repr(m)`` is a valid codegen-shaped constructor string."""
    r = repr(IrMap(IrTuple(IrStr("a"), IrInt(1))))
    assert r.startswith("IrMap(")
    assert "IrTuple" in r and "IrStr" in r and "IrInt" in r


# ── Key-miss is a hard, doubly-typed error ────────────────────────────


def test_key_miss_is_doubly_typed_ir_key_error():
    """A subscript miss raises :exc:`IrKeyError` — both
    ``UnsupportedConstructError`` and ``KeyError``."""
    m = names_map()
    with pytest.raises(IrKeyError) as exc_info:
        _ = m[IrStr("?")]
    assert isinstance(exc_info.value, UnsupportedConstructError)
    assert isinstance(exc_info.value, KeyError)


def test_eval_miss_raises():
    """``m.eval`` on a missing key raises a key error."""
    with pytest.raises(UnsupportedConstructError):
        names_map().eval(names_map(), IrStr("?"), ())


def test_duplicate_keys_raise():
    """Duplicate keys at construction raise :exc:`UnsupportedConstructError`."""
    with pytest.raises(UnsupportedConstructError):
        IrMap(IrTuple(IrStr("dup"), IrInt(1)), IrTuple(IrStr("dup"), IrInt(2)))


# ── Immutability ──────────────────────────────────────────────────────


def test_setattr_and_delattr_raise():
    """``setattr``/``delattr`` on a frozen map raise :class:`TypeError`."""
    m = names_map()
    with pytest.raises(TypeError):
        setattr(m, "foo", "bar")
    with pytest.raises(TypeError):
        delattr(m, "_table")


# ── IrTypeMap dispatch ────────────────────────────────────────────────


def test_irtype_map_exact_type_hit():
    """An ``IrLiteral``-keyed action runs when the node is an IrLiteral."""
    disp = IrTypeMap(
        IrTuple(IrLiteral, IrLambda(lambda _d, n, _nc: IrStr(f"lit:{n}"))),
        IrTuple(IrSelf, IrThis()),
    )
    assert disp.eval(disp, IrLiteral("x"), ()) == IrStr("lit:x")


def test_irtype_map_mro_fallback():
    """An ``IrSelf``-keyed arm catches ``IrRuleRef`` via MRO fallback."""
    disp = IrTypeMap(
        IrTuple(IrLiteral, IrLambda(lambda _d, n, _nc: IrStr(f"lit:{n}"))),
        IrTuple(IrSelf, IrThis()),
    )
    ref = IrRuleRef("r")
    assert disp.eval(disp, ref, ()) == ref


def test_irtype_map_miss_raises():
    """An ``IrTypeMap`` with no matching MRO entry raises a key error."""
    with pytest.raises(UnsupportedConstructError):
        IrTypeMap(IrTuple(IrLiteral, IrThis())).eval(IrNone, IrRuleRef("r"), ())


# ── IR_DEFAULT fallback ───────────────────────────────────────────────


def test_resolve_exact_key_wins_over_default():
    """An exact-key hit takes priority over :data:`IR_DEFAULT`."""
    assert default_map().resolve(IrStr("a")) == IrStr("hitA")


def test_resolve_miss_falls_through_to_default():
    """A miss resolves to the :data:`IR_DEFAULT` value instead of raising."""
    assert default_map().resolve(IrStr("zzz")) == IrStr("DEFAULT")


def test_eval_miss_runs_default_value():
    """``eval(d, n, nc)`` on a missed key evaluates the default's value.

    For a self-evaluating scalar default, eval returns it directly.
    """
    result = default_map().eval(default_map(), IrStr("zzz"), ())
    assert result == IrStr("DEFAULT")


def test_resolve_miss_without_default_raises():
    """A miss with no :data:`IR_DEFAULT` registered raises :exc:`IrKeyError`."""
    with pytest.raises(IrKeyError):
        IrMap(IrTuple(IrStr("a"), IrStr("hitA"))).resolve(IrStr("zzz"))


def test_getitem_and_contains_bypass_default():
    """``__getitem__``/``__contains__`` are explicit-key only — no fallback."""
    m = default_map()
    assert IR_DEFAULT in m
    assert IrStr("zzz") not in m
    with pytest.raises(IrKeyError):
        _ = m[IrStr("zzz")]


def test_getitem_exact_key_with_default_registered():
    """``m[IrStr("a")]`` returns its value even when a default is present."""
    assert default_map()[IrStr("a")] == IrStr("hitA")


def test_irtype_map_honours_default_fallback():
    """A type miss resolves to :data:`IR_DEFAULT`; an exact type still wins."""
    disp = IrTypeMap(
        IrTuple(IrLiteral, IrStr("lit")),
        IrTuple(IR_DEFAULT, IrStr("fallback")),
    )
    assert disp.resolve(IrRuleRef("r")) == IrStr("fallback")
    assert disp.resolve(IrLiteral("x")) == IrStr("lit")


def test_homogeneous_map_construction_and_resolve_unaffected():
    """Plain homogeneous maps construct and resolve correctly (no default regression)."""
    m = IrMap(
        IrTuple(IrStr("a"), IrStr("x")),
        IrTuple(IrStr("b"), IrStr("y")),
    )
    assert m.resolve(IrStr("a")) == IrStr("x")
    assert m.resolve(IrStr("b")) == IrStr("y")


def test_heterogeneous_map_with_default_constructs_without_error():
    """A map mixing real dyads with a default dyad constructs cleanly."""
    m = IrMap(
        IrTuple(IrStr("key1"), IrStr("val1")),
        IrTuple(IR_DEFAULT, IrStr("default_val")),
    )
    assert m.resolve(IrStr("key1")) == IrStr("val1")
    assert m.resolve(IrStr("other")) == IrStr("default_val")


# ── IR_DEFAULT sentinel ───────────────────────────────────────────────


def test_ir_default_is_singleton_and_distinct():
    """:data:`IR_DEFAULT` is a singleton, repr's to its name, and is distinct."""
    assert type(IR_DEFAULT)() is IR_DEFAULT
    assert repr(IR_DEFAULT) == "IR_DEFAULT"
    assert IR_DEFAULT is not IrNone
    assert IR_DEFAULT != IrStr("x")


# ── IrMultiMap mutable surface (live reads) ───────────────────────────


def test_multimap_files_and_reads_live_bucket():
    """``mm += (k, v)`` files; ``mm[k]`` returns the live backing bucket."""
    mm: IrMultiMap = IrMultiMap()
    mm += (IrStr("k"), IrStr("v1"))
    mm += (IrStr("k"), IrStr("v2"))
    bucket = mm[IrStr("k")]
    assert list(bucket) == [IrStr("v1"), IrStr("v2")]
    assert bucket is getattr(mm, "_table")[IrStr("k")]  # live, not a snapshot copy


def test_multimap_live_read_sees_appends():
    """A held live read reflects later appends (index iteration is safe)."""
    mm: IrMultiMap = IrMultiMap()
    mm += (IrStr("k"), IrStr("v1"))
    live = mm[IrStr("k")]
    mm += (IrStr("k"), IrStr("v2"))
    assert list(live) == [IrStr("v1"), IrStr("v2")]


def test_multimap_missing_key_reads_empty():
    """A miss reads the empty tuple and ``__contains__`` is False — never raises."""
    mm: IrMultiMap = IrMultiMap()
    assert not tuple(mm[IrStr("absent")])
    assert IrStr("absent") not in mm


def test_multimap_contains_after_filing():
    """``k in mm`` is True once a bucket is filed."""
    mm: IrMultiMap = IrMultiMap()
    mm += (IrStr("k"), IrStr("v"))
    assert IrStr("k") in mm


def test_multimap_identity_equality_and_hash():
    """A mutable map is its own value — identity eq/hash."""
    a: IrMultiMap = IrMultiMap()
    b: IrMultiMap = IrMultiMap()
    alias = a
    assert alias == a  # identity eq: same object compares equal
    assert a != b
    assert hash(a) == id(a)


def test_multimap_table_slot_available_for_subclasses():
    """The backing dict is the shared ``_table`` slot (the subclass contract)."""
    mm: IrMultiMap = IrMultiMap()
    mm += (IrStr("k"), IrStr("v"))
    assert getattr(mm, "_table") == {IrStr("k"): [IrStr("v")]}


# ── building a map from a table, without reaching for the slot ────────────


def test_ir_map_from_table_matches_the_dyad_constructor() -> None:
    """``from_table`` and ``IrMap(*dyads)`` build the same map."""
    dyads = (IrTuple(IrStr("b"), IrInt(2)), IrTuple(IrStr("a"), IrInt(1)))
    pairs = [(d[0], d[1]) for d in dyads]
    assert IrMap.from_table(pairs) == IrMap(*dyads)


def test_ir_map_from_table_canonicalises_whatever_order_it_is_given() -> None:
    """``IrMap``'s order is a property of its KEYS, not of the caller's list.

    The reader that motivated this builds a map from a file, and a file can be
    edited. Sorting here is what keeps ``_table`` canonical by construction
    rather than by trusting the input — the export fixpoint cannot catch a
    wrongly-ordered map, because a wrong order re-encodes to itself.
    """
    forward = [(IrStr("a"), IrInt(1)), (IrStr("b"), IrInt(2))]
    assert list(IrMap.from_table(reversed(forward)).keys()) == [IrStr("a"), IrStr("b")]
    assert list(IrMap.from_table(forward).keys()) == [IrStr("a"), IrStr("b")]


def test_from_table_refuses_a_duplicate_key() -> None:
    """A repeated key is a corrupt table, not a last-one-wins merge."""
    with pytest.raises(UnsupportedConstructError, match="duplicate key"):
        IrMap.from_table([(IrStr("a"), IrInt(1)), (IrStr("a"), IrInt(2))])


def test_multimap_from_table_keeps_the_order_it_is_given() -> None:
    """The base container has no canonical order to impose — insertion is it.

    ``IrMultiMap`` documents insertion order and is identity-equal, so
    canonicalising its table would be inventing an invariant it does not have.
    """
    pairs = [(IrStr("b"), [1]), (IrStr("a"), [2])]
    assert list(IrMultiMap.from_table(pairs).keys()) == [IrStr("b"), IrStr("a")]


def test_from_table_needs_no_reach_into_the_private_slot() -> None:
    """The point of the constructor: a caller never names ``_table``.

    The compiled-payload reader rebuilt a mapping with
    ``object.__setattr__(obj, "_table", …)``, hard-coding a private slot across
    a boundary no import makes visible — rename the slot and every artefact
    ever written decodes wrong, silently.
    """
    built = IrMap.from_table([(IrStr("k"), IrInt(1))])
    assert built[IrStr("k")] == IrInt(1)
    assert built == IrMap(IrTuple(IrStr("k"), IrInt(1)))
