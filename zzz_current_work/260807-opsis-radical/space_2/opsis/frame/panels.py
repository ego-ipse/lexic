"""Where each surface sits, and the room it sits in.

`space.arrange` has always computed the arrangement; space_1 shipped the tree
to the leaf and let it do the placing, which is how a room could end up
disagreeing with what was drawn in it. The tree is applied HERE now — the
same measurement, one reader of it — and what leaves is a rectangle with a
header already drawn.
"""

from __future__ import annotations

from opsis.frame.marks import Frame
from opsis.frame.tones import runs

__all__ = ["Room", "called", "chrome", "rooms"]

GAP = 8.0
HEAD = 26.0
TAB = 15.0


class Room:
    """A surface's rectangle, and who it shares the column with."""

    __slots__ = ("at", "h", "mates", "name", "w", "x", "y")

    def __init__(
        self,
        name: str,
        x: float,
        y: float,
        w: float,
        h: float,
        mates: tuple[str, ...],
        at: int,
    ) -> None:
        self.name = name
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.mates = mates
        self.at = at


def _tokens(shape: str) -> list[str]:
    return shape.replace("(", " ( ").replace(")", " ) ").split()


def _read(said: list[str], i: int) -> tuple[object, int]:
    """One node of the arrangement — a name, or a split and its two sides."""
    if said[i] != "(":
        return said[i], i + 1
    kind = said[i + 1]
    if kind == "t":
        j = i + 3
        mates: list[str] = []
        while said[j] != ")":
            mates.append(said[j])
            j += 1
        return ("t", int(said[i + 2]), tuple(mates)), j + 1
    left, j = _read(said, i + 3)
    right, k = _read(said, j)
    return (kind, float(said[i + 2]), left, right), k + 1


def _place(
    node: object, x: float, y: float, w: float, h: float, out: list[Room]
) -> None:
    """A node of the tree, into the rectangle it was handed."""
    if isinstance(node, str):
        out.append(Room(node, x, y, w, h, (node,), 0))
        return
    if not isinstance(node, tuple):
        return
    if node[0] == "t":
        _, at, mates = node
        showing = mates[min(int(at), len(mates) - 1)]
        out.append(
            Room(str(showing), x, y, w, h, tuple(str(m) for m in mates), int(at))
        )
        return
    kind, share, left, right = node
    if kind == "h":
        cut = w * float(share)
        _place(left, x, y, cut - GAP / 2, h, out)
        _place(right, x + cut + GAP / 2, y, w - cut - GAP / 2, h, out)
    else:
        cut = h * float(share)
        _place(left, x, y, w, cut - GAP / 2, out)
        _place(right, x, y + cut + GAP / 2, w, h - cut - GAP / 2, out)


def rooms(shape: str, x: float, y: float, w: float, h: float) -> list[Room]:
    """The arrangement, as the rectangles it means."""
    said = _tokens(shape)
    if not said:
        return []
    node, _ = _read(said, 0)
    out: list[Room] = []
    _place(node, x, y, w, h, out)
    return out


def called(title: str, name: str) -> str:
    """What a room is called on a tab — its title's own first words."""
    head = title.partition(" · ")[0]
    return head.removeprefix("THE ").casefold() if head else name


def chrome(
    said: Frame, room: Room, titles: dict[str, str], keep: bool = True
) -> tuple[float, float, float, float]:
    """Draw a room — its panel, its header, its tabs — and hand back the inside.

    :param titles: each surface's ``NAME · what it is for``, by surface name.
    :param keep: whether this room can be popped out and cloned.
    """
    said.box(room.x, room.y, room.w, room.h, "panel")
    said.line(room.x, room.y, room.x + room.w, room.y, "hair")
    said.line(room.x, room.y + HEAD, room.x + room.w, room.y + HEAD, "hair")
    at = room.x + 12
    if len(room.mates) > 1:
        for mate in room.mates:
            here = mate == room.name
            says = called(titles.get(mate, ""), mate)
            wide = runs("label", says) + 20
            said.box(at, room.y + 5, wide, TAB, "lit" if here else "panel")
            said.text(at + 10, room.y + 16, "ink" if here else "dim", says, wide - 14)
            said.hit(at, room.y + 5, wide, TAB, "surface", mate)
            at += wide + 4
    else:
        name, _, what = titles.get(room.name, room.name.upper()).partition(" · ")
        said.text(at, room.y + 17, "label", name)
        said.text(
            at + runs("label", name) + 14, room.y + 17, "note", what, room.w - 160
        )
    if keep:
        for i, (glyph, kind) in enumerate((("⧉", "pop"), ("⊞", "clone"))):
            cx = room.x + room.w - 26 - i * 22
            said.text(cx, room.y + 17, "dim", glyph)
            said.hit(cx - 4, room.y + 4, 20, 18, kind, room.name)
    said.hit(room.x, room.y + HEAD, room.w, room.h - HEAD, "scroll", room.name)
    return (room.x, room.y + HEAD, room.w, room.h - HEAD)
