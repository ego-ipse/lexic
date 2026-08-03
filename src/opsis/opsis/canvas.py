"""Element constructors on lexic's own layout docs — no template blobs.

Every page opsis emits is an ``IrDoc`` tree rendered by lexic's layout
algebra, which is why there is no templating here and no markup held in
strings. Escaping is intrinsic rather than remembered: text and every
attribute value escape, and :func:`raw` is the one deliberate
pass-through for markup another renderer produced.
"""

from __future__ import annotations

from html import escape

from lexic.ir import IrCat, IrDoc, IrLine, IrText, render

__all__ = ["el", "html", "raw", "text", "void"]


def text(body: str) -> IrDoc:
    """An escaped text leaf."""
    return _lines(escape(body))


def raw(body: str) -> IrDoc:
    """A pass-through leaf — markup, styles, script bodies."""
    return _lines(body)


def _lines(body: str) -> IrDoc:
    """Text as the algebra wants it — newlines are real break nodes.

    ``IrText`` refuses an embedded newline, because it would break the
    layout's column accounting; a multi-line string becomes a
    concatenation with ``IrLine`` between its rows.
    """
    rows = body.split("\n")
    if len(rows) == 1:
        return IrText(body)
    parts: list[IrDoc] = []
    for i, row in enumerate(rows):
        if i:
            parts.append(IrLine("", ""))
        if row:
            parts.append(IrText(row))
    return IrCat(*parts)


def el(tag: str, attrs: dict[str, str | None] | None, *kids: IrDoc | str) -> IrDoc:
    """One element — attributes escaped, string children escaped.

    The doc check comes first: an ``IrText`` IS a ``str`` (a node is its
    payload), so a doc child must never be escaped twice.
    """
    parts: list[IrDoc] = [raw(f"<{tag}{_attrs(attrs)}>")]
    parts.extend(kid if isinstance(kid, IrDoc) else text(kid) for kid in kids)
    parts.append(raw(f"</{tag}>"))
    return IrCat(*parts)


def void(tag: str, attrs: dict[str, str | None] | None = None) -> IrDoc:
    """A void element — ``meta``, ``br`` and kin."""
    return raw(f"<{tag}{_attrs(attrs)}>")


def _attrs(attrs: dict[str, str | None] | None) -> str:
    """The attribute string — a ``None`` value renders bare."""
    if not attrs:
        return ""
    out = []
    for key, value in attrs.items():
        out.append(
            f" {key}" if value is None else f' {key}="{escape(value, quote=True)}"'
        )
    return "".join(out)


def html(doc: IrDoc) -> str:
    """Render a doc tree to its final text — flat, width-free."""
    return str(render(doc, None))
