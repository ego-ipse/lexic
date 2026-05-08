"""Sanity: new_gbnf package re-exports the right names."""

from __future__ import annotations

from lexic.grammars import new_gbnf


def test_imports():
    """Sanity: new_gbnf package re-exports the right names."""
    assert hasattr(new_gbnf, "GbnfEscapes")
    assert hasattr(new_gbnf, "META_GRAMMAR")
    assert hasattr(new_gbnf, "GbnfFlavour")
