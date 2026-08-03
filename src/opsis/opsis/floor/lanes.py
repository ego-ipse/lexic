"""Lanes — one language, spelled two ways, and whether that is true.

Two grammars are a lane when they mean the same language. That is a
claim, and this is where it gets checked rather than asserted: both are
canonicalised, and equal canonical forms is what ``≅`` means. Different
ones are not a failure — they are two different languages, said so.

The check is cheap and the answer is exact, so there is no reason for a
lane to be a label somebody applied.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrDoc
from lexic.ir.grammar.canonical import canonicalize
from opsis.opsis.draw.canvas import el
from opsis.opsis.draw.canvas import text as _text
from opsis.opsis.read.views import bounded, panel
from opsis.praxis.reading import FOREIGN

__all__ = ["Lane", "lane_of", "lane_view"]


class Lane(NamedTuple):
    """What two grammars turned out to be to each other."""

    same: bool
    why: str
    theirs: str
    ours: str


def lane_of(ours: IrAst, theirs: IrAst) -> Lane:
    """Whether two grammars are the same language, measured.

    Canonicalisation is language-preserving, so equal canonical forms
    means equal languages — and the forms themselves are shown, because
    "not the same" is only useful if you can see where they part.
    """
    try:
        a, b = canonicalize(ours), canonicalize(theirs)
    except FOREIGN as exc:
        return Lane(False, f"{type(exc).__name__}: {exc}", "", "")
    if a == b:
        return Lane(
            True, f"≅ · both canonicalise to {len(list(a.rules))} rules", "", ""
        )
    return Lane(
        False,
        f"not the same language · {len(list(a.rules))} rules against "
        f"{len(list(b.rules))}",
        str(b),
        str(a),
    )


def lane_view(title: str, other: str, lane: Lane) -> IrDoc:
    """The equivalence claim between two grammars, and what differs.

    ``≅`` is drawn as a measured verdict rather than a decoration: it
    was computed from both canonical forms just now, and when it does
    not hold, both forms are here to be read.
    """
    rows: list[IrDoc] = [
        el(
            "div",
            {"class": "claim ok" if lane.same else "claim no"},
            _text(f"{title} ≅ {other}" if lane.same else f"{title} ≇ {other}"),
            el("em", None, _text(lane.why)),
        ),
    ]
    if not lane.same and lane.ours:
        rows.append(_side(title, lane.ours))
        rows.append(_side(other, lane.theirs))
    return panel(
        "canonicalisation is language-preserving, so equal canonical forms "
        "means equal languages — this was computed, not labelled",
        *rows,
    )


def _side(name: str, form: str) -> IrDoc:
    """One canonical form, as far as a window can hold it."""
    shown, note = bounded(form, 4000)
    return el(
        "div",
        {"class": "row"},
        el("span", {"class": "name"}, _text(name)),
        el("div", {"class": "note"}, _text(note or "canonical form")),
        el("pre", {"class": "src"}, _text(shown)),
    )
