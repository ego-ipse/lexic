"""Tests for lexic.parsing.product.abi.construction — what a completion builds WITH.

The load-bearing distinction this module draws is that only a LICENSED
:class:`RecordConstructor` may resolve a positional construction licence, and
:class:`SymbolConstructor` never does. Both resolution functions
(:func:`record_construction`, :func:`symbol_construction`) are tested against
that distinction directly, including the case where a class COULD answer
``fast_construct`` but the record does not ask for it — the case a stray
``if hasattr(cls, "fast_construct")`` would get silently wrong.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import NamedTuple

from lexic.parsing.product.abi.construction import (
    BoundSymbol,
    RecordConstructor,
    SymbolConstructor,
    record_construction,
    symbol_construction,
)

# ── defaults ─────────────────────────────────────────────────────────────


def test_record_constructor_defaults():
    """A bare RecordConstructor names only its class; everything else defaults."""
    entry = RecordConstructor(cls=tuple)
    assert not entry.names
    assert not entry.optional
    assert entry.defaults == MappingProxyType({})
    assert entry.matched_field == ""
    assert entry.licensed is False


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


# ── record_construction: the licence gate ───────────────────────────────


class _Licensable(NamedTuple):
    """A stand-in declared record: a real class with a real ``fast_construct``."""

    a: int
    b: int = 9

    @classmethod
    def fast_construct(cls):
        """Return this record's positional construction licence."""
        return (cls, {"b": 9}, ("a", "b"))


def test_record_construction_resolves_the_declared_fields():
    """The resolved view carries the entry's class, names, optional and matched."""
    entry = RecordConstructor(
        cls=_Licensable,
        names=("a",),
        optional=(0,),
        defaults=MappingProxyType({"b": 9}),
        matched_field="b",
    )
    resolved = record_construction(entry)
    assert resolved.call is _Licensable
    assert resolved.names == ("a",)
    assert resolved.optional == frozenset({0})
    assert resolved.defaults == {"b": 9}
    assert resolved.matched == "b"


def test_record_construction_grants_no_licence_when_not_asked():
    """A class that COULD answer fast_construct is not consulted unless licensed=True.

    The tell-tale defect this catches: resolving the licence off ``hasattr``
    instead of off the authored flag would silently grant every eligible class
    a fast path the declaration never asked for.
    """
    entry = RecordConstructor(cls=_Licensable, names=("a", "b"), licensed=False)
    resolved = record_construction(entry)
    assert resolved.licence is None


def test_record_construction_grants_the_licence_when_asked():
    """licensed=True resolves the licence by calling the class's own method."""
    entry = RecordConstructor(cls=_Licensable, names=("a", "b"), licensed=True)
    resolved = record_construction(entry)
    assert resolved.licence == (_Licensable, {"b": 9}, ("a", "b"))


def test_record_construction_optional_becomes_a_frozenset():
    """``optional`` is converted to a frozenset — order-independent membership."""
    entry = RecordConstructor(cls=tuple, names=("x", "y"), optional=(1, 0, 1))
    resolved = record_construction(entry)
    assert resolved.optional == frozenset({0, 1})
    assert resolved.optional.__class__ is frozenset


# ── symbol_construction: never a licence ────────────────────────────────


def test_symbol_construction_resolves_the_declared_fields():
    """The resolved view carries the bound symbol's callable, names and matched."""
    entry = BoundSymbol(apply=str, names=("value",), optional=(0,), matched="tail")
    resolved = symbol_construction(entry)
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
    resolved = symbol_construction(entry)
    assert resolved.licence is None


def test_symbol_construction_defaults_to_empty_defaults_mapping():
    """symbol_construction never fills the defaults mapping — only records do."""
    entry = BoundSymbol(apply=str)
    resolved = symbol_construction(entry)
    assert resolved.defaults == MappingProxyType({})
