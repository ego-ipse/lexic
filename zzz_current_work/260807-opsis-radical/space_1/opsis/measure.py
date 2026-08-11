"""How big a track is, in the instrument's own unit: characters.

The leaf measured this with `measureText`, which made the shape of a
railroad a fact about a font in a browser — underivable, uncheckable, and
different in every window. Every other surface here is measured in columns
and rows; a railroad is too. The leaf multiplies by the cell it happens to
be drawing in, which is the one thing it genuinely knows.

A box is `(wide, tall, spine)` — how many columns it needs, how many rows,
and how far down the row the through-line runs, so a sequence can join its
children at one height.
"""

from __future__ import annotations

from praxis.reading import columns

__all__ = ["Box", "boxes"]

# in characters and rows. A token's padding, the gap between things in a
# sequence, the gap between the arms of a choice, and the room a loop's
# return line needs above or below what it wraps.
PAD = 2
GAP = 3
VGAP = 1
LOOP = 2
BRACKET = 6


class Box:
    """One node's room, in columns and rows, and where its line runs."""

    __slots__ = ("label", "spine", "tall", "wide")

    def __init__(self, wide: float, tall: float, spine: float, label: str = "") -> None:
        self.wide = wide
        self.tall = tall
        self.spine = spine
        self.label = label

    def wire(self) -> str:
        return f"{self.wide:.2f} {self.tall:.2f} {self.spine:.2f}"


def _leaf(kind: str, payload: str) -> Box:
    """A token: as wide as what it says, plus the room around the words."""
    said = {"nil": "ε", "class": f"[{payload}]"}.get(kind, payload or "ε")
    if len(said) > 30:
        said = said[:29] + "…"
    return Box(max(6.0, columns(said) + PAD * 2), 1.0, 0.5, said)


def _measure(node: tuple[str, str, list], out: list[Box]) -> Box:
    """This node's box, and every box under it, in pre-order."""
    kind, payload, kids = node
    here = Box(0, 0, 0)
    out.append(here)
    inner = [_measure(kid, out) for kid in kids]
    if kind == "seq" and inner:
        here.spine = max(box.spine for box in inner)
        here.wide = sum(box.wide for box in inner) + GAP * (len(inner) - 1)
        here.tall = here.spine + max(box.tall - box.spine for box in inner)
    elif kind == "alt" and inner:
        # the arms stack, and the choice needs room for the fork on each side
        here.wide = max(box.wide for box in inner) + BRACKET
        here.tall = sum(box.tall for box in inner) + VGAP * (len(inner) - 1)
        here.spine = inner[0].spine
    elif kind == "many" and inner:
        low, high = (payload.split() + ["1", "1"])[:2]
        bypass = low == "0"
        loops = high != "1"
        kid = inner[0]
        here.wide = kid.wide + 4
        here.tall = kid.tall + (LOOP if bypass else 0) + (LOOP if loops else 0)
        here.spine = kid.spine + (LOOP if bypass else 0)
    elif kind in ("not", "alpha") and inner:
        tag = "¬ none of" if kind == "not" else f"⟨{payload}⟩"
        kid = inner[0]
        here.wide = max(kid.wide + 2, columns(tag) + 2)
        here.tall = kid.tall + 1.5
        here.spine = kid.spine + 1
    else:
        said = _leaf(kind, payload)
        here.wide, here.tall, here.spine, here.label = (
            said.wide,
            said.tall,
            said.spine,
            said.label,
        )
    return here


def _tree(lines: list[str]) -> tuple[str, str, list]:
    """The track's own lines back into the nesting they describe."""
    root: tuple[str, str, list] = ("seq", "", [])
    stack: list[tuple[str, str, list]] = [root]
    for line in lines:
        depth, _, rest = line.partition(" ")
        if not depth.isdigit():
            continue
        kind, _, payload = rest.partition(" ")
        node = (kind, payload, [])
        at = int(depth)
        if at + 1 > len(stack):
            continue
        stack[at][2].append(node)
        stack[at + 1 :] = [node]
    kids = root[2]
    return kids[0] if len(kids) == 1 else root


def boxes(lines: list[str]) -> list[Box]:
    """Every node's room, in the order the track's lines arrive."""
    out: list[Box] = []
    _measure(_tree(lines), out)
    # the root's own box is first; the lines describe its children onward
    return out[1:] if len(out) > len(lines) else out
