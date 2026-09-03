"""Tests for lexic.parsing.product.abi.construction — what a completion builds WITH.

The load-bearing distinction this module draws is that only a LICENSED
:class:`RecordConstructor` may resolve a positional construction licence, and
:class:`SymbolConstructor` never does. Both resolution constructors
(:meth:`Construction.of_record`, :meth:`Construction.of_symbol`) are tested
against that distinction directly, including the case where a class COULD answer
``fast_construct`` but the record does not ask for it — the case a stray
``if hasattr(cls, "fast_construct")`` would get silently wrong.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import NamedTuple

from lexic.parsing.product.abi.construction import (
    BoundSymbol,
    Construction,
    ConstructionLicence,
    RecordConstructor,
    SymbolConstructor,
)

# ── defaults ─────────────────────────────────────────────────────────────


def test_record_constructor_defaults():
    """A bare RecordConstructor names only its class; everything else defaults."""
    entry = RecordConstructor(cls=tuple)
    assert not entry.names
    assert not entry.optional
    assert entry.defaults == MappingProxyType({})
    assert entry.matched_field == ""
    assert entry.licence is None


def test_symbol_constructor_defaults():
    """A bare SymbolConstructor names only its registry key."""
    entry = SymbolConstructor(symbol="absent_tail")
    assert entry.names == ()
    assert entry.optional == ()
    assert entry.matched == ""


def test_bound_symbol_defaults():
    """A bare BoundSymbol names only its resolved callable."""
    entry = BoundSymbol(apply=str)
    assert not entry.names
    assert not entry.optional
    assert entry.matched == ""


# ── Construction.of_record: the licence gate ───────────────────────────────


class _Licensable(NamedTuple):
    """A stand-in declared record — a real class a declaration can name."""

    a: int
    b: int = 9


_LICENCE = ConstructionLicence(_Licensable._make, {"b": 9}, ("a", "b"))
"""The licence a declarer would read off ``_Licensable`` and carry."""


def test_record_construction_resolves_the_declared_fields():
    """The resolved view carries the entry's class, names, optional and matched."""
    entry = RecordConstructor(
        cls=_Licensable,
        names=("a",),
        optional=(0,),
        defaults=MappingProxyType({"b": 9}),
        matched_field="b",
    )
    resolved = Construction.of_record(entry)
    assert resolved.call is _Licensable
    assert resolved.names == ("a",)
    assert resolved.optional == frozenset({0})
    assert resolved.defaults == {"b": 9}
    assert resolved.matched == "b"


def test_record_construction_grants_no_licence_when_none_is_declared():
    """A class that COULD be built positionally is not granted it by being able to.

    The tell-tale defect this catches: recovering the licence from the class
    (``hasattr``, ``getattr``) would silently grant every eligible class a fast
    path the declaration never carried.
    """
    entry = RecordConstructor(cls=_Licensable, names=("a", "b"))
    resolved = Construction.of_record(entry)
    assert resolved.licence is None


def test_record_construction_carries_the_declared_licence_unchanged():
    """A declared licence reaches the resolved view as the record it is."""
    entry = RecordConstructor(cls=_Licensable, names=("a", "b"), licence=_LICENCE)
    resolved = Construction.of_record(entry)
    assert resolved.licence is not None
    assert resolved.licence is _LICENCE
    assert resolved.licence.order == ("a", "b")


def test_record_construction_optional_becomes_a_frozenset():
    """``optional`` is converted to a frozenset — order-independent membership."""
    entry = RecordConstructor(cls=tuple, names=("x", "y"), optional=(1, 0, 1))
    resolved = Construction.of_record(entry)
    assert resolved.optional == frozenset({0, 1})
    assert resolved.optional.__class__ is frozenset


# ── Construction.of_symbol: never a licence ────────────────────────────────


def test_symbol_construction_resolves_the_declared_fields():
    """The resolved view carries the bound symbol's callable, names and matched."""
    entry = BoundSymbol(apply=str, names=("value",), optional=(0,), matched="tail")
    resolved = Construction.of_symbol(entry)
    assert resolved.call is str
    assert resolved.names == ("value",)
    assert resolved.optional == frozenset({0})
    assert resolved.matched == "tail"


def test_symbol_construction_never_grants_a_licence():
    """SymbolConstructor has no ``licensed`` field — the licence is always None.

    A surface transform is a callable, never a declared record class, so the
    positional fast path — which needs a class's own ``fast_construct`` — has
    nothing to resolve here even in principle.
    """
    entry = BoundSymbol(apply=str, names=("a",))
    resolved = Construction.of_symbol(entry)
    assert resolved.licence is None


def test_symbol_construction_defaults_to_empty_defaults_mapping():
    """Construction.of_symbol never fills the defaults mapping — only records do."""
    entry = BoundSymbol(apply=str)
    resolved = Construction.of_symbol(entry)
    assert resolved.defaults == MappingProxyType({})
