"""Where things sit — a tidy tree, from nothing but who reads whom.

Layout is opsis's own work rather than lexic's, and it is derived every
time rather than stored: a reading knows what it is and what reads it,
and would be the same reading laid out any other way.
"""

from __future__ import annotations

__all__ = ["COL", "ORIGIN", "ROW", "layout"]

COL = 470
"""Horizontal step between siblings."""

ROW = 300
"""Vertical step between a reader and what it reads."""

ORIGIN = (520, 240)
"""Where the first root sits."""


def layout(parents: dict[str, str], idents: list[str]) -> dict[str, tuple[int, int]]:
    """Where every reading sits, from nothing but who reads whom.

    Leaves take the next free column and a parent centres over its
    children, so the picture is a tidy tree without anyone having said
    so. Readings nobody reads are roots, laid out left to right in the
    order they arrived.

    :param parents: reading ident → the ident that reads it.
    :param idents: every reading, in the order they were opened.
    :returns: ident → (x, y).
    """
    kids: dict[str, list[str]] = {ident: [] for ident in idents}
    for child, parent in parents.items():
        if parent in kids and child in kids:
            kids[parent].append(child)
    roots = [i for i in idents if parents.get(i, "") not in kids]
    place: dict[str, tuple[int, int]] = {}
    slot = 0

    def visit(ident: str, depth: int) -> float:
        nonlocal slot
        here = kids[ident]
        if not here:
            column = float(slot)
            slot += 1
        else:
            spread = [visit(kid, depth + 1) for kid in here]
            column = sum(spread) / len(spread)
        place[ident] = (
            ORIGIN[0] + int(column * COL),
            ORIGIN[1] + depth * ROW,
        )
        return column

    for root in roots:
        visit(root, 0)
        slot += 1  # a gap, so one tree never crowds the next
    return place
