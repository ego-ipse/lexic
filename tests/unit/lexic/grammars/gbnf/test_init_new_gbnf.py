"""Sanity: gbnf package re-exports the right names."""

from __future__ import annotations

from lexic.grammars import gbnf


def test_imports():
    """Sanity: gbnf package re-exports the right names."""
    assert hasattr(gbnf, "GbnfEscapes")
    assert hasattr(gbnf, "META_GRAMMAR")
    assert hasattr(gbnf, "GbnfFlavour")
