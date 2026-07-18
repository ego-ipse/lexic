"""Tests for compile/foldkit.py — the shared authored-fold vocabulary.

``ALT`` and ``passthrough`` are the build-path unification seed: every
hand-authored grammar+fold pair (notation, the module self-grammar) reuses
these SAME objects rather than each defining its own copy.
"""

from __future__ import annotations

from lexic.compile import notation, selfgrammar
from lexic.compile.foldkit import ALT, passthrough
from lexic.parsing import RuleFold


def test_alt_is_an_alternation_rule_fold():
    """ALT is a RuleFold whose kind is "alternation" with no bound fields."""
    assert isinstance(ALT, RuleFold)
    assert ALT.kind == "alternation"
    assert ALT.n_items == 0
    assert ALT.fields == ()


def test_alt_ctor_is_unused_and_returns_none():
    """The alternation ctor slot is ignored by the fold; it returns None."""
    assert ALT.ctor() is None


def test_passthrough_returns_its_argument_unchanged():
    """passthrough is a pure identity function over any value."""
    sentinel = object()
    assert passthrough(sentinel) is sentinel
    assert passthrough("x") == "x"
    assert passthrough(0) == 0
    assert passthrough(None) is None


def test_notation_reuses_the_same_alt_and_passthrough_objects():
    """notation.py consumes foldkit's ALT/passthrough BY IDENTITY, not a copy."""
    assert getattr(notation, "_ALT") is ALT
    assert notation.passthrough is passthrough


def test_selfgrammar_reuses_the_same_alt_and_passthrough_objects():
    """selfgrammar.py consumes foldkit's ALT/passthrough BY IDENTITY too."""
    assert selfgrammar.ALT is ALT
    assert selfgrammar.passthrough is passthrough
