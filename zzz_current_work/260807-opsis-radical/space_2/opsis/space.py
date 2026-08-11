"""The arrangement — where every surface goes, decided here.

Every arrangement before this one was a shape someone liked: reader narrow,
document wide, the rest stacked beside. Measuring says that shape was
backwards — the reader needs 70 columns and the document 25 — which is why
the grammar was cut off mid-rule in every frame while the document had space
to spare.

So the arrangement is COMPUTED, and it is computed HERE. The leaf receives a
tree and applies it; it decides nothing about where anything lives. Three
relations, and every surface declares which one it is in:

- **beside** — its own column, sized by what it asked for;
- **tabbed** — two views of ONE subject share a column, so each gets the
  whole width when it is the one you are looking at. The relations graph
  spent four rounds being crushed into a slice of the reader's column when
  what it needed was the reader's column;
- **stacked** — a surface and its companion split a column vertically,
  because the spine is read AT the cursor the chart is scrubbing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from praxis.reading import Facet

__all__ = ["FLOOR", "arrange", "columns_of", "held", "shares"]

# Below this a monospace column shows nothing but ellipsis: a name, a colon
# and a hint of the body. Measured off the shortest useful rule line.
FLOOR = 32


def shares(facets: Sequence[Facet], columns: int) -> dict[str, int]:
    """Columns per surface, in proportion to what each one needs."""
    wanted = sum(facet.wide for facet in facets) or 1
    return {
        facet.name: max(FLOOR, round(columns * facet.wide / wanted)) for facet in facets
    }


def columns_of(facets: Sequence[Facet]) -> list[list[Facet]]:
    """The surfaces grouped into columns, in the order they were declared.

    A facet's ``column`` is the subject it belongs to; two facets naming the
    same column occupy one column together, tabbed or stacked as they say.
    """
    out: list[list[Facet]] = []
    seen: dict[str, list[Facet]] = {}
    for facet in facets:
        key = facet.column or facet.name
        if key not in seen:
            seen[key] = []
            out.append(seen[key])
        seen[key].append(facet)
    return out


def _group(
    group: Sequence[Facet],
    showing: dict[str, int],
    taken: Callable[[float], float] = lambda measured: measured,
) -> str:
    """One column's contents — a leaf, a tab set, or a vertical split."""
    if len(group) == 1:
        return group[0].name
    if group[0].relation == "stacked":
        # the share is the first surface's height against the pair's
        top = group[0].tall / max(1, sum(f.tall for f in group))
        share = taken(min(0.8, max(0.2, round(top, 3))))
        return (
            f"(v {round(share, 3)} {group[0].name} {_group(group[1:], showing, taken)})"
        )
    # WHICH TAB IS SHOWING is remembered here, with the rest of how you are
    # looking at this reading. The leaf keeping it meant a reload dropped
    # back to the first tab, and the server could not say what you were on.
    at = showing.get(group[0].column, 0)
    return f"(t {max(0, min(at, len(group) - 1))} {' '.join(f.name for f in group)})"


def arrange(
    facets: Sequence[Facet],
    columns: int = 200,
    showing: dict[str, int] | None = None,
    dragged: Sequence[float] = (),
) -> str:
    """The arrangement as a value the leaf applies without deciding anything.

    Left to right in the order the surfaces were declared, each split's share
    being that side's columns over what remains — so the tree says the same
    thing the measurements do.
    """
    groups = columns_of(facets)
    if not groups:
        return ""
    # a column asks for what its WIDEST member asks for: tab-mates take turns
    # at the full width, so the column is not the sum of their appetites
    given = shares(facets, columns)
    wide = [max(given[f.name] for f in group) for group in groups]
    on = showing or {}
    # a hand that dragged a seam has said something the measurement cannot
    # know. Its numbers come back in the order the splits are produced, and
    # they win — the measurement is where a layout STARTS, not a cage.
    hand = list(dragged)
    seen = [0]

    def taken(measured: float) -> float:
        """This split's share: what the hand said about it, or the measurement.

        A hand that has moved one seam has said nothing about the others, and
        the placeholder for that is negative — a share is a fraction, so no
        real one can be.
        """
        at = seen[0]
        seen[0] += 1
        said = hand[at] if at < len(hand) else -1.0
        return measured if said < 0 else said

    def split(at: int) -> str:
        if at == len(groups) - 1:
            return _group(groups[at], on, taken)
        rest = sum(wide[at + 1 :])
        share = taken(round(wide[at] / max(1, wide[at] + rest), 3))
        return f"(h {round(share, 3)} {_group(groups[at], on, taken)} {split(at + 1)})"

    return split(0)


def held(shape: str, facets: Sequence[Facet]) -> str:
    """A shape the HAND made, if it still describes these surfaces.

    Measurement decides where a surface starts; a hand that moved one has
    said something measurement cannot know, and recomputing over it on the
    next frame throws that away. The shape is kept only while it names
    exactly the surfaces in play — a stale one would place what is gone and
    drop what arrived.
    """
    named = {
        word.strip("()")
        for word in shape.split()
        if word.strip("()") and not word.strip("()")[0].isdigit()
    } - {"h", "v", "t"}
    return shape if named == {facet.name for facet in facets} else ""


# where in a surface a drop means WHICH relation: the outer quarters split,
# the middle tabs. `wire.js`'s own thresholds.
EDGE = 0.28


def zone_at(across: float, down: float) -> str:
    """What dropping at this point in a surface would MEAN."""
    if across < EDGE:
        return "left"
    if across > 1 - EDGE:
        return "right"
    if down < EDGE:
        return "top"
    if down > 1 - EDGE:
        return "bottom"
    return "tab"


def without(tree: str, name: str) -> str:
    """The arrangement with one surface taken out of it, and nothing else.

    A leaf's removal collapses the split that held it — its sibling takes the
    whole box. The LAST leaf stays: an arrangement of nothing is not an
    arrangement, it is a blank screen with a bug behind it.
    """
    node = _parse(tree)
    left = _drop(node, name)
    return "" if left is None else _spell(left)


def moved(tree: str, name: str, target: str, zone: str, showing: int = 1) -> str:
    """One surface, put somewhere else — the shape `moveLeaf` makes.

    Dropping on a side splits the target and takes half; dropping in the
    middle tabs the two together. This is the whole of a topology change, and
    it is a SHAPE, which is why it is not recomputed from measurement after.
    """
    if name == target:
        return tree
    node = _parse(tree)
    left = _drop(node, name)
    if left is None:
        return tree

    def split(said: object) -> object:
        """That node, halved, with the newcomer on the side it was dropped."""
        kind = "h" if zone in ("left", "right") else "v"
        first = zone in ("left", "top")
        return (kind, 0.5, name if first else said, said if first else name)

    def into(said: object) -> object:
        if said == target:
            return ("t", showing, (target, name)) if zone == "tab" else split(said)
        if not isinstance(said, tuple):
            return said
        if said[0] == "t":
            # A TAB GROUP IS ONE REGION. Dropping on the side of a tabbed
            # surface splits the region it is showing in — you cannot put
            # something beside one tab and not the others, because there is
            # only one box there. Dropping in the middle joins the set.
            if target not in said[2]:
                return said
            return ("t", said[1], (*said[2], name)) if zone == "tab" else split(said)
        return (said[0], said[1], into(said[2]), into(said[3]))

    return _spell(into(left))


def _parse(tree: str) -> object:
    said = tree.replace("(", " ( ").replace(")", " ) ").split()
    node, _ = _take(said, 0)
    return node


def _take(said: list[str], i: int) -> tuple[object, int]:
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
    left, j = _take(said, i + 3)
    right, k = _take(said, j)
    return (kind, float(said[i + 2]), left, right), k + 1


def _drop(node: object, name: str) -> object | None:
    """That leaf, gone — and whatever held it collapsed onto its sibling."""
    if node == name:
        return None
    if not isinstance(node, tuple):
        return node
    if node[0] == "t":
        mates = tuple(m for m in node[2] if m != name)
        if not mates:
            return None
        if len(mates) == 1:
            return mates[0]
        return ("t", min(node[1], len(mates) - 1), mates)
    left, right = _drop(node[2], name), _drop(node[3], name)
    if left is None:
        return right
    if right is None:
        return left
    return (node[0], node[1], left, right)


def _spell(node: object) -> str:
    if not isinstance(node, tuple):
        return str(node)
    if node[0] == "t":
        return f"(t {node[1]} {' '.join(str(m) for m in node[2])})"
    return f"({node[0]} {node[1]} {_spell(node[2])} {_spell(node[3])})"
