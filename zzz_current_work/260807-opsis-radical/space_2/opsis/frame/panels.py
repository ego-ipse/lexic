"""Where each facet sits — the arrangement tree, applied.

Facets are REGIONS with hairline seams, never windows: they abut, they carry
a one-pixel left and top border, and there is no gap, no panel fill and no
shadow between them. `space.arrange` has always computed the tree; space_1
shipped it to the leaf to place, which is how a region could end up
disagreeing with what was drawn in it. It is walked here now.

The head of a region is `.facet h2`: the name in cool at 10.5px, its own
sentence beside it in dim, and whatever selects that facet carries.
"""

from __future__ import annotations

from opsis.frame.marks import Frame
from opsis.frame.tones import runs

__all__ = ["Region", "Seam", "Walk", "head", "walked"]

# .facet h2 { padding: 8px 14px 6px } over a 12px line
HEAD = 27.0
PAD = 14.0
# .tabbar { height: 22px }
TABS = 22.0


class Region:
    """A facet's rectangle, and who it shares the region with."""

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


class Seam:
    """A hairline two regions meet on — and the split it stands for.

    Seams are numbered in the order the tree produces its splits, which is
    the order `arrange` reads dragged shares back in. That correspondence is
    the mechanism: a hand moves seam 2, and seam 2 is what the next
    arrangement is measured against.
    """

    __slots__ = ("across", "at", "h", "sits", "w", "x", "y")

    def __init__(
        self, at: int, x: float, y: float, w: float, h: float, across: bool, sits: float
    ) -> None:
        self.at = at
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.across = across
        self.sits = sits


class Walk:
    """One walk of an arrangement tree — its regions, and the seams between."""

    __slots__ = ("regions", "seams")

    def __init__(self) -> None:
        self.regions: list[Region] = []
        self.seams: list[Seam] = []

    def take(self, said: list[str], i: int) -> tuple[object, int]:
        """One node — a facet's name, a tab group, or a split and its sides."""
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
        left, j = self.take(said, i + 3)
        right, k = self.take(said, j)
        return (kind, float(said[i + 2]), left, right), k + 1

    def put(self, node: object, x: float, y: float, w: float, h: float) -> None:
        """A node of the tree, into the rectangle it was handed."""
        if isinstance(node, str):
            self.regions.append(Region(node, x, y, w, h, (node,), 0))
            return
        if not isinstance(node, tuple):
            return
        if node[0] == "t":
            _kind, showing, mates = node
            at = max(0, min(int(showing), len(mates) - 1))
            self.regions.append(
                Region(str(mates[at]), x, y, w, h, tuple(str(m) for m in mates), at)
            )
            return
        kind, share, left, right = node
        at = len(self.seams)
        if kind == "h":
            cut = w * float(share)
            self.seams.append(Seam(at, x + cut - 2, y, 4, h, True, float(share)))
            self.put(left, x, y, cut, h)
            self.put(right, x + cut, y, w - cut, h)
        else:
            cut = h * float(share)
            self.seams.append(Seam(at, x, y + cut - 2, w, 4, False, float(share)))
            self.put(left, x, y, w, cut)
            self.put(right, x, y + cut, w, h - cut)


def walked(tree: str, x: float, y: float, w: float, h: float) -> Walk:
    """The arrangement tree, as the rectangles and seams it means."""
    out = Walk()
    said = tree.replace("(", " ( ").replace(")", " ) ").split()
    if said:
        node, _ = out.take(said, 0)
        out.put(node, x, y, w, h)
    return out


def called(title: str) -> tuple[str, str]:
    """A facet's title, split the way its head sets it: the name, then the rest."""
    name, _, rest = title.partition("·")
    return name.strip(), rest.strip()


def head(
    said: Frame,
    region: Region,
    titles: dict[str, str],
    controls: list[tuple[str, str, str, bool]],
) -> tuple[float, float, float, float]:
    """Draw a region's seams, tab strip and head; hand back what is left.

    :param controls: what this facet's head carries — `(said, kind, goes, on)`.
    """
    # .facet { border-left: 1px solid --hair; border-top: 1px solid --hair }
    said.line(region.x, region.y, region.x, region.y + region.h, "hair")
    said.line(region.x, region.y, region.x + region.w, region.y, "hair")
    y = region.y
    if len(region.mates) > 1:
        _tabs(said, region, titles)
        y += TABS
    name, rest = called(titles.get(region.name, region.name))
    said.text(region.x + PAD, y + 18, "ftitle", name)
    at = region.x + PAD + runs("ftitle", name) + 10
    if rest:
        said.text(at, y + 18, "fsub", rest, region.w - (at - region.x) - 24)
    _controls(said, region, y, controls)
    said.line(region.x, y + HEAD, region.x + region.w, y + HEAD, "hair")
    said.hit(region.x, y + HEAD, region.w, region.h - HEAD, "scroll", region.name)
    return (region.x, y + HEAD, region.w, region.h - (y - region.y) - HEAD)


def _tabs(said: Frame, region: Region, titles: dict[str, str]) -> None:
    """.tabbar — a t-node's leaves, as the strip that switches between them."""
    said.box(region.x, region.y, region.w, TABS, "field2")
    said.line(region.x, region.y + TABS, region.x + region.w, region.y + TABS, "hair")
    at = region.x + 6
    for mate in region.mates:
        word = called(titles.get(mate, mate))[0].removeprefix("THE ").casefold()
        wide = runs("chip", word) + 20
        here = mate == region.name
        if here:
            said.box(at, region.y + 2, wide, TABS - 2, "field")
        said.line(at, region.y + 2, at, region.y + TABS, "cool" if here else "hair")
        said.line(
            at + wide,
            region.y + 2,
            at + wide,
            region.y + TABS,
            "cool" if here else "hair",
        )
        said.line(at, region.y + 2, at + wide, region.y + 2, "cool" if here else "hair")
        said.text(at + 10, region.y + 15, "cool" if here else "chip", word)
        said.hit(at, region.y + 2, wide, TABS - 2, "tab", mate)
        at += wide + 2


def _controls(
    said: Frame,
    region: Region,
    y: float,
    controls: list[tuple[str, str, str, bool]],
) -> None:
    """The selects a head carries — field2, hairline, dim mono, right-aligned."""
    if not controls:
        return
    wides = [runs("chip", word) + 10 for word, _kind, _goes, _on in controls]
    at = region.x + region.w - 10 - sum(wides) - 6 * len(controls)
    for (word, kind, goes, on), wide in zip(controls, wides, strict=True):
        said.box(at, y + 6, wide, 15, "field2")
        for x1, y1, x2, y2 in (
            (at, y + 6, at + wide, y + 6),
            (at, y + 21, at + wide, y + 21),
            (at, y + 6, at, y + 21),
            (at + wide, y + 6, at + wide, y + 21),
        ):
            said.line(x1, y1, x2, y2, "cool" if on else "hair")
        said.text(at + 5, y + 17, "cool" if on else "chip", word)
        said.hit(at, y + 6, wide, 15, kind, goes)
        at += wide + 6
