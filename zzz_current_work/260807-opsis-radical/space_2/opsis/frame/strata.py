"""THE STRATA — the session pulled back, so the whole climb is one picture.

`praxis.strata` has written this ladder since the first build and nothing has
ever drawn it: every rung walked, the one above it, and the doors each rung
holds. What lives here is only the reading of that text into a picture — the
cards, their little depth bands, and what each one says about itself.

It is the one thing that takes the whole frame rather than a region, because
what it shows is not a facet of the reading: it is where the reading SITS.
"""

from __future__ import annotations

from opsis.frame.marks import Frame
from opsis.frame.tones import runs

__all__ = ["Card", "draw", "read"]

CARD = 268.0
LANE = 300.0


class Card:
    """One reading on the ladder, and what is known about it."""

    __slots__ = ("band", "here", "label", "lane", "level", "said", "visited")

    def __init__(self, lane: int, level: int, visited: bool, label: str) -> None:
        self.lane = lane
        self.level = level
        self.visited = visited
        self.label = label
        self.band: list[int] = []
        self.said = ""
        self.here = False


class Door:
    """A room a rung holds — its values, its machine, its artefacts."""

    __slots__ = ("facts", "kind", "label", "lane", "pid")

    def __init__(self, pid: str, lane: int, kind: str, label: str, facts: str) -> None:
        self.pid = pid
        self.lane = lane
        self.kind = kind
        self.label = label
        self.facts = facts


def read(wire: str) -> tuple[list[Card], list[Door], int]:
    """The ladder as it was written — cards, doors, and where you stand."""
    cards: dict[int, Card] = {}
    doors: list[Door] = []
    here = 0
    for line in wire.split("\n"):
        parts = line.split(" ")
        if line.startswith("#STRATA") and len(parts) > 2:
            here = int(parts[2])
        elif parts[0] == "c" and len(parts) > 5:
            cards[int(parts[1])] = Card(
                int(parts[3]), int(parts[2]), parts[5] == "1", " ".join(parts[6:])
            )
        elif parts[0] == "k" and len(parts) > 6 and int(parts[1]) in cards:
            card = cards[int(parts[1])]
            card.said = (
                f"{int(parts[2]):,} chars · {int(parts[3]):,} spans · "
                f"{parts[4]} rules · {parts[5]}s"
                + ("" if parts[6] == "1" else " · UNFAITHFUL")
            )
        elif parts[0] == "b" and len(parts) > 2 and int(parts[1]) in cards:
            cards[int(parts[1])].band = [int(n) for n in parts[2:] if n.isdigit()]
        elif parts[0] == "P" and len(parts) > 6:
            label, _, facts = " ".join(parts[6:]).partition("\t")
            doors.append(Door(parts[1], int(parts[2]), parts[4], label, facts))
    for at, card in cards.items():
        card.here = at == here
    return [cards[at] for at in sorted(cards)], doors, here


def draw(said: Frame, wire: str, wide: int, tall: int) -> None:
    """The climb, as columns: one per thing, its readings and its doors inside."""
    cards, doors, _here = read(wire)
    said.box(0, 0, wide, tall, "field")
    said.text(34, 38, "title", "THE STRATA")
    said.text(
        34 + runs("title", "THE STRATA") + 16,
        38,
        "fsub",
        "the session pulled back — click a rung to travel, a door to enter",
    )
    said.hit(wide - 40, 24, 24, 20, "strata", "off")
    said.text(wide - 40, 38, "dim", "✕")
    x = 34.0
    for card in cards:
        _card(said, card, x, 74.0)
        y = 74.0 + 96
        for door in [d for d in doors if d.lane == card.lane]:
            _door(said, door, x, y)
            y += 52
        x += LANE
        if x > wide - CARD:
            break


def _card(said: Frame, card: Card, x: float, y: float) -> None:
    """One rung: what it is, its numbers, and the shape of its own reading."""
    tone = "warm" if card.here else ("hair" if card.visited else "dimmer")
    for x1, y1, x2, y2 in (
        (x, y, x + CARD, y),
        (x, y + 84, x + CARD, y + 84),
        (x, y, x, y + 84),
        (x + CARD, y, x + CARD, y + 84),
    ):
        said.line(x1, y1, x2, y2, tone)
    said.text(x + 10, y + 20, "ink" if card.visited else "dim", card.label, CARD - 20)
    _band(said, card, x + 10, y + 30)
    said.text(
        x + 10,
        y + 76,
        "fsub" if card.visited else "dimmer",
        card.said or "not yet visited — travel builds it",
        CARD - 20,
    )
    if not card.here:
        said.hit(x, y, CARD, 84, "rung", str(card.lane))


def _band(said: Frame, card: Card, x: float, y: float) -> None:
    """The little graph: how deep that reading goes across its own document.

    A card with a number and no shape says almost nothing about the reading it
    stands for.
    """
    said.box(x, y, CARD - 20, 26, "field2")
    if not card.band:
        return
    deep = max(card.band) or 1
    step = (CARD - 20) / len(card.band)
    for i, at in enumerate(card.band):
        high = 24 * at / deep
        said.box(x + i * step, y + 25 - high, max(1.0, step - 0.5), high, "modelband2")


def _door(said: Frame, door: Door, x: float, y: float) -> None:
    """A room this rung holds — a value, a machine, a set of artefacts."""
    edge = {"value": "cool", "compiler": "violet", "artefacts": "green"}.get(
        door.kind, "hair"
    )
    said.line(x, y, x, y + 44, edge)
    said.line(x + 2, y, x + CARD, y, "hair")
    said.line(x + 2, y + 44, x + CARD, y + 44, "hair")
    said.line(x + CARD, y, x + CARD, y + 44, "hair")
    said.text(x + 10, y + 16, "chip", door.kind.upper(), face="chip")
    # what is LEFT, not a guess at it: the label starts after the kind and
    # runs to the card's own edge
    at = x + 10 + runs("chip", door.kind.upper()) + 16
    said.text(at, y + 16, "ink", door.label, x + CARD - at - 10)
    said.text(x + 10, y + 34, "fsub", door.facts, CARD - 20)
    said.hit(x, y, CARD, 44, "place", door.pid)
