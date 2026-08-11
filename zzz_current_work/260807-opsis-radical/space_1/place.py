"""The arrangement — give each surface the room it asked for, or a window.

Every arrangement before this one was a shape someone liked: reader narrow,
document wide, the rest stacked beside. Measuring says that shape was
backwards — the reader needs 93 columns and the document 30 — which is why
the grammar was cut off mid-rule in every frame while the document had space
to spare.

So the arrangement is COMPUTED from what the surfaces need. Shares are their
widths, normalised. A surface that cannot fit even at its share does not get
squeezed: it is named as wanting a window, because a view crushed below its
own size is not a smaller view, it is a wrong one.
"""

from __future__ import annotations

from collections.abc import Sequence

from read import Facet

__all__ = ["arrange", "windowed"]

# Below this a monospace column shows nothing but ellipsis: a name, a colon
# and a hint of the body. Measured off the shortest useful rule line.
FLOOR = 32


def shares(facets: Sequence[Facet], columns: int) -> dict[str, int]:
    """Columns per surface, in proportion to what each one needs."""
    wanted = sum(facet.wide for facet in facets) or 1
    return {
        facet.name: max(FLOOR, round(columns * facet.wide / wanted)) for facet in facets
    }


# What a surface can lose before it stops being itself. Below this it is not
# a smaller view, it is a wrong one — measured against what it ASKED for, not
# against a floor, because a floor says "64 columns is enough" to a graph
# that needs 132.
ENOUGH = 0.7


def windowed(facets: Sequence[Facet], columns: int) -> list[str]:
    """The surfaces this width cannot honour — they want a window, not a share.

    Stated rather than silently crushed: the instrument says "this does not
    fit here" the way it says every other refusal.
    """
    given = shares(facets, columns)
    return [f.name for f in facets if given[f.name] < f.wide * ENOUGH]


def arrange(facets: Sequence[Facet], columns: int = 200) -> str:
    """The arrangement as a value: splits carrying the share each side gets.

    Left to right in the order the surfaces were declared, each split's share
    being that side's columns over what remains — so the tree says the same
    thing the measurements do.
    """
    if not facets:
        return ""
    given = shares(facets, columns)
    names = [facet.name for facet in facets]
    left = given[names[0]]
    rest = sum(given[name] for name in names[1:])
    if len(names) == 1:
        return names[0]
    share = round(left / max(1, left + rest), 3)
    return f"(h {share} {names[0]} {arrange(facets[1:], rest)})"
