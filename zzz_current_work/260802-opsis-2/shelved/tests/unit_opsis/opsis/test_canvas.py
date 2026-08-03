"""Canvas contract — escaping, raw pass-through, attributes, void elements."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from opsis.opsis.draw.canvas import el, html, raw, text


def test_text_escapes_angle_brackets_ampersand_and_quote() -> None:
    """An injected script tag cannot survive into the rendered output."""
    rendered = html(text('<script>alert("x")</script> & co'))
    assert "<script>" not in rendered
    assert "</script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&amp;" in rendered


def test_raw_does_not_escape() -> None:
    """A pass-through leaf carries its markup through unchanged."""
    rendered = html(raw("<b>bold</b>"))
    assert rendered == "<b>bold</b>"


def test_el_with_attrs_none_emits_no_attributes() -> None:
    """No attrs dict means the tag opens bare."""
    rendered = html(el("div", None, "hi"))
    assert rendered == "<div>hi</div>"


def test_el_omits_a_none_valued_attribute() -> None:
    """An attribute whose value is ``None`` renders bare, not as ``key="None"``."""
    rendered = html(el("input", {"disabled": None, "value": "x"}))
    assert "disabled" in rendered
    assert 'disabled="' not in rendered
    assert 'value="x"' in rendered


def test_el_escapes_attribute_values() -> None:
    """An attribute value carrying a quote cannot break out of its attribute."""
    rendered = html(el("div", {"title": '" onmouseover="x'}))
    assert '" onmouseover="x"' not in rendered
    assert "&quot;" in rendered


def test_void_elements_emit_no_closing_tag() -> None:
    """``br``, ``input`` and ``img`` are void — one tag, never a matching close.

    Asked of ``el`` itself, because whether a tag closes is a fact about
    the tag: a caller that reaches for the wrong spelling is the bug
    this element set exists to make impossible.
    """
    for tag in ("br", "input", "img"):
        rendered = html(el(tag, {"src": "x"} if tag == "img" else None))
        assert rendered.startswith(f"<{tag}")
        assert f"</{tag}>" not in rendered


def test_a_void_element_refuses_children() -> None:
    """HTML has nowhere to put them, so asking is a refusal, not a render."""
    with pytest.raises(UnsupportedConstructError, match="void element"):
        el("br", None, "nowhere to go")
