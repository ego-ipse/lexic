"""Tests for opsis.opsis._canvas — element constructors with intrinsic escaping."""

from __future__ import annotations

from opsis.opsis._canvas import el, html, raw, text, void


def test_text_escapes():
    """text() escapes markup-significant characters; the raw tag never survives."""
    out = html(text("<b>&"))
    assert "&lt;b&gt;&amp;" in out
    assert "<b>" not in out


def test_el_escapes_attrs_and_children_but_not_doc_kids():
    """el() escapes attribute values and string children; a doc child passes through unescaped."""
    out = html(el("a", {"href": 'x"y'}, "z"))
    assert "&quot;" in out
    assert '"x"y"' not in out

    passthrough = html(el("i", None, raw("<x>")))
    assert "<x>" in passthrough


def test_newlines_survive():
    """A newline in text() renders as a literal newline, not a break marker."""
    assert html(text("a\nb")) == "a\nb"


def test_void_has_no_closing_tag():
    """void() renders a self-closing element with no matching close tag."""
    out = html(void("meta", {"charset": "utf-8"}))
    assert out == '<meta charset="utf-8">'
    assert "</meta>" not in out
