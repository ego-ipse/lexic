"""The presentation half — an open per-type draw table over a tkinter canvas.

The table mirrors lexic's consumer contract: open registration, MRO resolution,
and a raising ``UnsupportedConstructError`` default. A node kind without an
entry becomes a drawn refusal carrying the exception's own words — never a blank.
"""

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrInt, IrNamedTuple, IrNoneType, IrSelf, IrStr

from scene import Path, Style

Box = tuple[int, int, int, int]
FontCache = dict[tuple[str, int, str, int], tkfont.Font]

MONO_FAMILIES = ("JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono")
SANS_FAMILIES = ("Inter", "DejaVu Sans", "Liberation Sans")


class Frame:
    """One frame's cursor — canvas, style, addresses, and the hit list it fills."""

    def __init__(
        self,
        cv: tk.Canvas,
        st: Style,
        cache: FontCache,
        mono_family: str,
        sans_family: str,
        hover: Path | None,
        selection: Path | None,
        buffer: str | None,
    ) -> None:
        self.cv = cv
        self.st = st
        self.cache = cache
        self.mono_family = mono_family
        self.sans_family = sans_family
        self.hover = hover
        self.selection = selection
        self.buffer = buffer
        self.hits: list[tuple[Box, Path]] = []
        self.refusals: list[str] = []

    def font(self, role: str, delta: int = 0, weight: str = "normal") -> tkfont.Font:
        """The cached font for a role at the style's size plus ``delta``."""
        size = int(self.st.text) + delta
        key = (role, delta, weight, size)
        if key not in self.cache:
            family = self.mono_family if role == "mono" else self.sans_family
            self.cache[key] = tkfont.Font(family=family, size=size, weight=weight)
        return self.cache[key]

    def text(
        self,
        x: float,
        y: float,
        s: str,
        fill: str,
        font: tkfont.Font,
        anchor: str = "nw",
        width: int = 0,
    ) -> Box:
        """Draw a text item and return its bounding box.

        ``s`` is coerced to exact ``str``: Tcl 9 renders a ``str`` subclass (an
        ``IrStr``) as an opaque object handle — a bare pointer number on screen.
        """
        item = self.cv.create_text(x, y, text=str(s), fill=fill, font=font, anchor=anchor)
        if width:
            self.cv.itemconfigure(item, width=width)
        x1, y1, x2, y2 = self.cv.bbox(item)
        return (x1, y1, x2, y2)

    def region(self, path: Path, box: Box) -> None:
        """Record a hit region and halo it when it is the hover or the selection."""
        self.hits.append((box, path))
        if path == self.selection:
            self.outline(box, str(self.st.warm))
        elif path == self.hover:
            self.outline(box, str(self.st.dim))

    def outline(self, box: Box, colour: str) -> None:
        """A halo rectangle slightly outside ``box``."""
        x1, y1, x2, y2 = box
        self.cv.create_rectangle(x1 - 3, y1 - 2, x2 + 3, y2 + 2, outline=colour)


DrawFn = Callable[[Frame, IrSelf, Path, int, int], Box]
TABLE: dict[type, DrawFn] = {}


def register(kind: type, fn: DrawFn) -> None:
    """Add one presentation entry — the only way a kind becomes drawable."""
    TABLE[kind] = fn


def presentation_for(node: IrSelf) -> DrawFn:
    """The nearest registered entry along the node's MRO, or a raising refusal."""
    for base in type(node).__mro__:
        if base in TABLE:
            return TABLE[base]
    chain = " → ".join(c.__name__ for c in type(node).__mro__[:4])
    raise UnsupportedConstructError(
        f"opsis: no presentation registered for {type(node).__name__} "
        f"(mro {chain} …) — the table is open: register one entry, nothing else changes"
    )


def draw_subject(f: Frame, node: IrSelf, path: Path, x: int, y: int) -> Box:
    """Any node through the table; a missing entry becomes a drawn refusal."""
    try:
        fn = presentation_for(node)
    except UnsupportedConstructError as refusal:
        f.refusals.append(str(refusal))
        return draw_refusal(f, str(refusal), x, y)
    return fn(f, node, path, x, y)


def draw_refusal(f: Frame, words: str, x: int, y: int) -> Box:
    """The refusal card — the exception's own words, in red, boxed."""
    body = f.text(x + 10, y + 8, words, str(f.st.red), f.font("mono", -1), width=548)
    frame = (x, y, max(body[2] + 10, x + 568), body[3] + 8)
    f.cv.create_rectangle(*frame, outline=str(f.st.red))
    return frame


def spell_payload(value: IrSelf | int | str) -> str:
    """A leaf's payload as the glyphs to draw — empty strings stay visible."""
    if isinstance(value, str):
        return value if value else "''"
    return str(int(value))


def draw_scalar(f: Frame, node: IrSelf | int | str, path: Path, x: int, y: int) -> Box:
    """A value leaf drawn as its payload — editing draws the buffer in its place."""
    editing = path == f.selection and f.buffer is not None
    spelling = f.buffer + "▍" if editing and f.buffer is not None else spell_payload(node)
    colour = str(f.st.warm) if editing else str(f.st.ink)
    box = f.text(x, y, spelling, colour, f.font("mono"))
    f.region(path, box)
    return box


def draw_none(f: Frame, node: IrSelf, path: Path, x: int, y: int) -> Box:
    """Absence drawn as a socket — present, addressable, never a blank."""
    label = f.text(x + 8, y + 4, "IrNone", str(f.st.dim), f.font("mono"))
    box = (x, y, label[2] + 8, label[3] + 4)
    f.cv.create_rectangle(*box, outline=str(f.st.dim), dash=(4, 3))
    f.region(path, box)
    return box


def draw_value(f: Frame, value: IrSelf | int | str, path: Path, x: int, y: int) -> Box:
    """One record element — a node through the table, a plain payload as itself."""
    if isinstance(value, IrSelf):
        return draw_subject(f, value, path, x, y)
    box = draw_scalar(f, value, path, x, y)
    tag = f.text(
        box[2] + 12, y + 2, f"plain {type(value).__name__} payload", str(f.st.dim), f.font("sans", -3)
    )
    return (box[0], box[1], tag[2], max(box[3], tag[3]))


def draw_record(f: Frame, node: IrSelf, path: Path, x: int, y: int) -> Box:
    """A record as named rows over the same elements again as an indexed strip.

    The by-name rows and the by-index cells carry the SAME path per element, so
    hovering either halos both — the record is one thing read two ways.
    """
    pad = int(f.st.pad)
    names = type(node)._fields
    name_font = f.font("sans", -1)
    name_w = max(name_font.measure(n) for n in names) + pad
    x0, yc, right = x + pad, y, x + pad
    for i, name in enumerate(names):
        f.text(x0, yc, name, str(f.st.dim), name_font)
        vbox = draw_value(f, node[i], path + (i,), x0 + name_w, yc)
        right = max(right, vbox[2])
        yc = max(vbox[3], yc + name_font.metrics("linespace")) + max(4, pad // 2)
    cell, sx = 20, x0
    for i in range(len(names)):
        cbox = (sx, yc, sx + cell, yc + cell)
        f.cv.create_rectangle(*cbox, outline=str(f.st.cool))
        f.cv.create_text(
            sx + cell // 2, yc + cell // 2, text=str(i), fill=str(f.st.cool), font=f.font("mono", -2)
        )
        f.region(path + (i,), cbox)
        sx += cell + 6
    yc += cell
    f.cv.create_line(x, y, x, yc, fill=str(f.st.cool))
    return (x, y, max(right, sx), yc)


register(IrStr, draw_scalar)
register(IrInt, draw_scalar)
register(IrNoneType, draw_none)
register(IrNamedTuple, draw_record)
