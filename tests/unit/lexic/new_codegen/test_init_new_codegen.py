"""Sanity: new_codegen package importable."""

from __future__ import annotations

from lexic import new_codegen


def test_imports():
    """Test that new_codegen can be imported."""
    assert hasattr(new_codegen, "collect_aliases")
