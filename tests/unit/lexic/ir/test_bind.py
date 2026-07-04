"""Tests for ir/bind.py — the IrBind field-binding marker."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.bind import BIND_MODES, IrBind


def test_bind_carries_item_mode_semantic():
    """The three fields read back by name."""
    bind = IrBind(2, "model", False)
    assert (bind.item, bind.mode, bind.semantic) == (2, "model", False)


def test_bind_semantic_defaults_true():
    """A two-argument bind is a semantic field."""
    assert IrBind(0, "text").semantic is True


@pytest.mark.parametrize("mode", BIND_MODES)
def test_bind_accepts_every_documented_mode(mode: str):
    """All four fold modes construct."""
    assert IrBind(0, mode).mode == mode


def test_bind_rejects_an_unknown_mode():
    """A typo'd mode fails at construction, not at fold time."""
    with pytest.raises(UnsupportedConstructError, match="unknown mode"):
        IrBind(0, "txet")


def test_bind_equality_is_structural():
    """Same slot, mode and flag compare equal."""
    assert IrBind(1, "gtext") == IrBind(1, "gtext")
    assert IrBind(1, "gtext") != IrBind(1, "text")


def test_bind_repr_is_codegen_with_default_elided():
    """repr reproduces the constructor call; semantic=True drops off."""
    assert repr(IrBind(3, "models")) == "IrBind(3, 'models')"
    assert repr(IrBind(3, "models", False)) == "IrBind(3, 'models', False)"
