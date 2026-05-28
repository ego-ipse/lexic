"""Sanity: gbnf package re-exports the right names."""

from __future__ import annotations

from lexic.grammars import gbnf


def test_imports():
    """Sanity: gbnf package re-exports the right names."""
    assert hasattr(gbnf, "GBNF_ESCAPES")
    assert hasattr(gbnf, "GBNF_ACTIONS")
    assert hasattr(gbnf, "META_GRAMMAR")
    assert hasattr(gbnf, "GBNF_FLAVOUR")
