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
