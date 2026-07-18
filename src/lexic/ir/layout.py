"""Layout algebra — width-aware document combinators on the record spine.

Wadler-style pretty-printing as IR data: a *doc* tree describes text with
its break opportunities, and :func:`render` solves the line breaks against a
width deterministically. Emitters build docs; nothing here knows what the
text means.

The combinators:

- :class:`IrText` — literal text (the node IS the string; never a newline);
- :class:`IrLine` — a break opportunity: its ``flat`` text when the
  enclosing group stays flat, ``pre`` + newline + indent when it breaks;
- :class:`IrCat` — concatenation (the node IS its parts tuple);
- :class:`IrNest` — adds relative indent to every break inside its doc;
- :class:`IrGroup` — the fit unit: renders flat iff its flattened text plus
  the rest of the current line (the sheet's pending work up to the next
  break) fits the width, else every direct :class:`IrLine` in it breaks
  (inner groups re-decide on their own line).

Behavior is intrinsic to the nodes (:meth:`IrDoc.layout` for rendering,
:meth:`IrDoc.scan` for the fit lookahead — a new doc type implements both)
against a mutable :class:`Sheet` cursor; :func:`render` is a flat driver
over the sheet's explicit stack, so rendering depth never rides the Python
stack.
"""

from __future__ import annotations

from typing import ClassVar, Self, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNamedTuple, IrNode, IrSelf, IrSeq, IrStr


class Sheet:
    """The render cursor — output parts, column, work stack, target width."""

    __slots__ = ("width", "col", "parts", "stack")

    def __init__(self, width: int) -> None:
        """Start an empty sheet against ``width``.

        :param width: Target maximum line width.
        """
        self.width = width
        self.col = 0
        self.parts: list[str] = []
        self.stack: list[tuple[int, bool, IrDoc]] = []

    def write(self, text: str) -> None:
        """Emit ``text`` on the current line and advance the column.

        :param text: Newline-free text.
        """
        self.parts.append(text)
        self.col += len(text)

    def newline(self, indent: int, pre: str = "") -> None:
        """Emit ``pre``, break the line, land at ``indent`` columns.

        :param indent: The new line's leading indent.
        :param pre: Broken-only text emitted before the newline.
        """
        self.parts.append(pre + "\n" + " " * indent)
        self.col = indent

    def fits(self, doc: IrDoc) -> bool:
        """Whether ``doc`` rendered flat, plus the rest of the current line,
        stays within the width.

        The lookahead scans ``doc`` in flat mode and then the sheet's pending
        work in its recorded modes, stopping at the first break that will
        actually be taken (an :class:`IrLine` in a non-flat frame) — the
        Wadler ``fits`` with the continuation included, so trailing
        separators AND a breaking line's broken-only ``pre`` text count
        against the line they land on.

        :param doc: The candidate group content.
        :returns: ``True`` when the line cannot overflow.
        """
        col = self.col
        # bottom..top of the pending stack, then the candidate on top — the
        # scan pops LIFO, i.e. candidate first, then the line's continuation.
        work: list[tuple[bool, IrDoc]] = [(fl, d) for _i, fl, d in self.stack]
        work.append((True, doc))
        while work:
            flat, node = work.pop()
            width, ends = node.scan(flat, work)
            col += width
            if col > self.width:
                return False
            if ends:
                return True
        return True


class IrDoc(IrNode[IrSelf, IrSelf]):
    """Role marker + protocol for layout nodes.

    :meth:`layout` performs the node's one rendering step against the sheet;
    :meth:`scan` is the fit-lookahead twin: ``(width contributed, line ends
    here)``, pushing children onto the scan's work list.
    """

    def layout(self, sheet: Sheet, indent: int, flat: bool) -> None:
        """Emit this node's text onto the sheet and/or push work.

        :param sheet: The render cursor (parts, column, stack, width).
        :param indent: Current indent (columns) for breaks.
        :param flat: Whether the enclosing group rendered flat.
        :raises UnsupportedConstructError: When the node type does not
            implement its rendering step.
        """
        raise UnsupportedConstructError(
            f"layout: {type(self).__name__} does not implement layout()"
        )

    def scan(self, flat: bool, work: list[tuple[bool, IrDoc]]) -> tuple[int, bool]:
        """One fit-lookahead step — ``(width contributed, line ends here)``.

        A breaking :class:`IrLine` still contributes its broken-only ``pre``
        text to the CURRENT line before ending it.

        :param flat: The scanning frame's flat mode.
        :param work: The scan's work list (push children here).
        :raises UnsupportedConstructError: When the node type does not
            implement its scan step.
        """
        raise UnsupportedConstructError(
            f"layout: {type(self).__name__} does not implement scan()"
        )


class IrText(IrDoc, IrStr):
    """Literal text — the node IS the string; newlines are refused.

    :class:`IrLine` is the only line device, so column accounting never has
    to scan text for embedded breaks.
    """

    def __new__(cls, text: str = "") -> Self:
        """Construct, refusing embedded newlines.

        :param text: The literal text.
        :raises UnsupportedConstructError: When ``text`` contains a newline.
        """
        if "\n" in text:
            raise UnsupportedConstructError(
                f"IrText: embedded newline in {text!r}; break with IrLine"
            )
        return cast(Self, super().__new__(cls, text))

    def layout(self, sheet: Sheet, indent: int, flat: bool) -> None:
        sheet.write(str(self))

    def scan(self, flat: bool, work: list[tuple[bool, IrDoc]]) -> tuple[int, bool]:
        return len(self), False


class IrLine(IrDoc, IrNamedTuple[str, str]):
    """A break opportunity.

    Renders as ``flat`` when the enclosing group stays flat, and as
    ``pre`` + newline + indent when it breaks — ``pre`` is the broken-only
    text (e.g. a trailing comma before a closing bracket:
    ``IrLine("", ",")``).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    flat: str = ""
    pre: str = ""

    def layout(self, sheet: Sheet, indent: int, flat: bool) -> None:
        if flat:
            sheet.write(self.flat)
            return
        sheet.newline(indent, self.pre)

    def scan(self, flat: bool, work: list[tuple[bool, IrDoc]]) -> tuple[int, bool]:
        if flat:
            return len(self.flat), False
        return len(self.pre), True


class IrCat(IrDoc, IrSeq[IrDoc]):
    """Concatenation — the node IS its parts tuple."""

    def layout(self, sheet: Sheet, indent: int, flat: bool) -> None:
        sheet.stack.extend((indent, flat, part) for part in self[::-1])

    def scan(self, flat: bool, work: list[tuple[bool, IrDoc]]) -> tuple[int, bool]:
        work.extend((flat, part) for part in self[::-1])
        return 0, False


class IrNest(IrDoc, IrNamedTuple[int, IrDoc]):
    """Relative indent for every break inside ``doc``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("doc",)
    indent: int
    doc: IrDoc

    def layout(self, sheet: Sheet, indent: int, flat: bool) -> None:
        sheet.stack.append((indent + self.indent, flat, self.doc))

    def scan(self, flat: bool, work: list[tuple[bool, IrDoc]]) -> tuple[int, bool]:
        work.append((flat, self.doc))
        return 0, False


class IrGroup(IrDoc, IrNamedTuple[IrDoc]):
    """The fit unit: flat iff the flattened group + line continuation fits.

    The lookahead treats a group in the continuation optimistically (scanned
    flat); if that group then breaks on its own line the estimate was merely
    conservative for it, never for this one.
    """

    doc: IrDoc

    def layout(self, sheet: Sheet, indent: int, flat: bool) -> None:
        sheet.stack.append((indent, flat or sheet.fits(self.doc), self.doc))

    def scan(self, flat: bool, work: list[tuple[bool, IrDoc]]) -> tuple[int, bool]:
        work.append((flat, self.doc))
        return 0, False


def render(doc: IrDoc, width: int = 88) -> str:
    """Render a doc against ``width`` — deterministic, explicit-stack.

    :param doc: The document to render.
    :param width: Target maximum line width; a line exceeds it only when it
        contains no break opportunity.
    :returns: The rendered text.
    """
    sheet = Sheet(width)
    sheet.stack.append((0, False, doc))
    while sheet.stack:
        indent, flat, node = sheet.stack.pop()
        node.layout(sheet, indent, flat)
    return "".join(sheet.parts)
