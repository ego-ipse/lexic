"""Element constructors on lexic's own layout docs — no template blobs.

Every page opsis emits is an ``IrDoc`` tree rendered by lexic's layout
algebra, which is why there is no templating here and no markup held in
strings. Escaping is intrinsic rather than remembered: text and every
attribute value escape, and :func:`raw` is the one deliberate
pass-through for markup another renderer produced.
"""

from __future__ import annotations

from html import escape

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrCat, IrDoc, IrLine, IrText, render

__all__ = ["VOID", "el", "html", "raw", "text"]


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


VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
"""Elements HTML closes for you — writing ``</br>`` is not markup."""


def el(tag: str, attrs: dict[str, str | None] | None, *kids: IrDoc | str) -> IrDoc:
    """One element — attributes escaped, string children escaped.

    Whether a tag closes is a fact about the tag, so it is decided here
    rather than by every caller remembering. Asking for children of a
    void element is a mistake worth hearing about, not one to render.

    The doc check comes first: an ``IrText`` IS a ``str`` (a node is its
    payload), so a doc child must never be escaped twice.

    :raises UnsupportedConstructError: When a void element is given
        children — HTML has nowhere to put them.
    """
    open_tag = raw(f"<{tag}{_attrs(attrs)}>")
    if tag not in VOID:
        kid_docs = [k if isinstance(k, IrDoc) else text(k) for k in kids]
        return IrCat(open_tag, *kid_docs, raw(f"</{tag}>"))
    if kids:
        raise UnsupportedConstructError(
            f"<{tag}> is a void element; it takes no children"
        )
    return open_tag


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
