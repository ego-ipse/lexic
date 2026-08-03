"""Element constructors on lexic layout docs — the page is an ``IrDoc``.

No template blob: every page opsis emits is a doc tree built from these
constructors and rendered by lexic's layout algebra. Escaping is
intrinsic — :func:`text` and attribute values escape, :func:`raw` is the
single deliberate pass-through (style bodies, script bodies, and markup
another renderer already produced).
"""

from __future__ import annotations

from html import escape

from lexic.ir import IrCat, IrDoc, IrLine, IrText, render

__all__ = ["el", "html", "raw", "text", "void"]


def text(s: str) -> IrDoc:
    """An escaped text leaf."""
    return _lines(escape(s))


def raw(s: str) -> IrDoc:
    """A pass-through leaf — pre-rendered markup, styles, script."""
    return _lines(s)


def _lines(s: str) -> IrDoc:
    """Text as the algebra wants it — newlines are :class:`IrLine` breaks."""
    rows = s.split("\n")
    if len(rows) == 1:
        return IrText(s)
    parts: list[IrDoc] = []
    for i, row in enumerate(rows):
        if i:
            parts.append(IrLine("", ""))
        if row:
            parts.append(IrText(row))
    return IrCat(*parts)


def el(tag: str, attrs: dict[str, str | None] | None, *kids: IrDoc | str) -> IrDoc:
    """One element — attributes escaped, string children escaped.

    The doc check comes first: an :class:`IrText` IS a ``str`` (the node
    is its payload), and a doc child must never be re-escaped.
    """
    parts: list[IrDoc] = [raw(f"<{tag}{_attrs(attrs)}>")]
    parts.extend(k if isinstance(k, IrDoc) else text(k) for k in kids)
    parts.append(raw(f"</{tag}>"))
    return IrCat(*parts)


def void(tag: str, attrs: dict[str, str | None] | None = None) -> IrDoc:
    """A void element (``meta`` and kin)."""
    return raw(f"<{tag}{_attrs(attrs)}>")


def _attrs(attrs: dict[str, str | None] | None) -> str:
    """The attribute string — ``None`` values render as bare attributes."""
    if not attrs:
        return ""
    out = []
    for key, val in attrs.items():
        out.append(f" {key}" if val is None else f' {key}="{escape(val, quote=True)}"')
    return "".join(out)


def html(doc: IrDoc) -> str:
    """Render a doc tree to its final text — flat, width-free."""
    return str(render(doc, None))
