"""Tests for opsis.opsis.scene — the scene substrate.

``visual(t)`` marks a payload type visual by MRO, not by wrapping; the
scene records (``Ring``/``Rail``/``Window``/``Space``) are frozen spine
citizens whose ``repr`` is the session file that ``load_ir`` reads back.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.compile.notation.parse import load_ir
from lexic.grammars import get_flavour
from lexic.ir import IrNone, IrRuleRef
from opsis.opsis import Ring as RingReExport
from opsis.opsis.scene import (
    OPSIS_SYMBOLS,
    Rail,
    Ring,
    Space,
    VisualNode,
    Window,
    visual,
)

GRAMMAR_TEXT = 'root ::= "x" num\nnum ::= [0-9]+\n'


def _scene():
    """Build a small scene over a real compiled grammar's rule payloads."""
    cg = compile_text(GRAMMAR_TEXT)
    rules = cg.grammar.rules
    ring1 = Ring("root", payload=rules[0])
    ring2 = Ring("num", payload=rules[1])
    rail = Rail(src="root", dst="num", label="ref")
    window = Window("detail", body=rules[1])
    return Space(ring1, ring2, rail, window)


def test_repr_fixpoint():
    """load_ir(repr(scene)) reproduces the same repr."""
    scene = _scene()
    assert repr(load_ir(repr(scene), symbols=OPSIS_SYMBOLS)) == repr(scene)


def test_structural_equality_round_trips():
    """load_ir(repr(scene)) is structurally equal to the original scene."""
    scene = _scene()
    assert load_ir(repr(scene), symbols=OPSIS_SYMBOLS) == scene


def test_visual_dispatches_via_mro():
    """A visual IrRuleRef still fires the payload's gbnf emit action."""
    node = visual(IrRuleRef)("member")
    assert str(get_flavour("gbnf").apply(node)) == "member"
    assert isinstance(node, VisualNode)
    assert isinstance(node, IrRuleRef)


def test_visual_is_memoised():
    """visual(t) synthesizes the marked subclass once per payload type."""
    assert visual(IrRuleRef) is visual(IrRuleRef)


def test_ring_is_frozen():
    """Setting an attribute on a Ring raises AttributeError."""
    ring = Ring("root")
    with pytest.raises(AttributeError):
        setattr(ring, "hue", "red")


def test_ring_is_its_field_tuple():
    """A Ring IS its field tuple: index, name access, and iteration agree."""
    ring = Ring("root", hue="magenta")
    assert ring[0] == ring.name
    assert len(ring) == 5
    assert list(ring) == ["root", IrNone, "magenta", 0, 0]


def test_ring_default_payload_is_ir_none():
    """A Ring with no payload defaults to IrNone, never Python None."""
    assert Ring("bare").payload is IrNone


def test_window_default_body_is_ir_none():
    """A Window with no body defaults to IrNone, never Python None."""
    assert Window("empty").body is IrNone


def test_ring_re_exported_from_package():
    """Ring is re-exported unchanged from the opsis.opsis package top-level."""
    assert RingReExport is Ring
