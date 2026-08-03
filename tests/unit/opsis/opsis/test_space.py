"""Tests for opsis.opsis.space — the scene's emit half."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import IrKeyError
from lexic.ir import IrNone, IrStr
from opsis.opsis.scene import Rail, Ring, Space, VisualNode, Window, visual
from opsis.opsis.space import page, render_scene

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


def test_fragment_and_page_are_deterministic():
    """render_scene and page render the same bytes across repeated calls."""
    scene = _scene()
    assert render_scene(scene) == render_scene(scene)
    assert page(scene) == page(scene)


def test_fragment_structure():
    """The fragment carries one wires svg, both rings, and the window frame."""
    scene = _scene()
    out = render_scene(scene)

    assert out.count('<svg id="wires"') == 1
    assert 'data-src="root" data-dst="num"' in out

    assert 'class="nd ring cyan" id="root"' in out
    assert 'class="nd ring cyan" id="num"' in out

    assert 'data-frame="detail"' in out
    assert "IrRule(&#x27;num&#x27;" in out


def test_ring_name_escapes_through_the_table():
    """A ring named with markup renders escaped, never a raw tag."""
    scene = Space(Ring("<script>x"))
    out = render_scene(scene)
    assert "&lt;script&gt;x" in out
    assert "<script>" not in out


def test_unregistered_visual_type_raises():
    """A visual node with no draw action raises IrKeyError — the open table's raising default."""
    stray = VisualNode.ensure(visual(IrStr)("stray"), "test: a visual leaf")
    scene = Space(stray)
    with pytest.raises(IrKeyError):
        render_scene(scene)


def test_window_with_ir_none_body_renders_empty_notation():
    """A Window whose body is IrNone renders an empty notation pre, never the text 'IrNone'."""
    scene = Space(Window("empty"))
    out = render_scene(scene)
    assert Window("empty").body is IrNone
    assert '<pre class="notation"></pre>' in out
    assert "IrNone" not in out
