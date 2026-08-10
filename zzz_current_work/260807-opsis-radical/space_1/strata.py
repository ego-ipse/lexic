"""The map between rooms — the relation graph, drawn.

Cards are relation instances; an instance that has never been focused is a
GHOST — it exists because the engine licenses the cast that would make it,
not because anyone listed it, and travelling is what makes it real. Lanes are
the chains those instances belong to, levels their distance from a root.

This is the graph the strip is a 1-D projection of; here it is the whole
picture, which is what the strip could never be.
"""

from __future__ import annotations

from reading import Reading
from relate import Relation, Session

__all__ = ["band", "cards", "frame"]

BUCKETS = 44

# The leaf draws a door per room KIND it knows; a relation kind it has never
# heard of gets no door, so the mapping is stated here rather than assumed.
DOOR = {"viewing": "value"}


def cards(session: Session) -> list[str]:
    """Every relation instance the session holds, in index order.

    Index is the address the leaf travels by, so it must not shuffle: the
    dict is insertion-ordered and instances are never removed.
    """
    return list(session.relations)


def band(relation: Relation) -> list[int]:
    """A card's own texture: how dense the parse is across the text."""
    if not isinstance(relation, Reading) or not relation.spans:
        return []
    chars = max(1, len(relation.document()))
    out = [0] * BUCKETS
    for span in relation.spans:
        at = min(BUCKETS - 1, (span.start * BUCKETS) // chars)
        out[at] += 1
    top = max(out) or 1
    return [round(count * 100 / top) for count in out]


def frame(session: Session) -> str:
    """The map, spelled. Held instances and ghosts alike — the graph as it is."""
    session.expand()
    order = cards(session)
    focus = order.index(session.focus) if session.focus in order else 0
    lanes: dict[str, int] = {}
    out = [f"#STRATA {len(order)} {focus}"]
    rows: list[str] = []
    for place, rid in enumerate(order):
        relation = session.relations[rid]
        root = session.strip(rid)[0]
        lane = lanes.setdefault(root, len(lanes))
        seen = 1 if relation.held else 0
        if not isinstance(relation, Reading):
            continue
        rows.append(
            f"c {place} {session.level(rid)} {lane} r {seen} {relation.label()}"
        )
        rows.extend(_facts(place, relation))
    for root, lane in lanes.items():
        out.append(f"L {lane} {session.relations[root].label()}")
    rows.extend(_rooms(session))
    return "\n".join([*out, *rows]) + "\n"


def _rooms(session: Session) -> list[str]:
    """Rooms that are not readings — they hang off the thing they are of."""
    out = []
    for rid, relation in session.relations.items():
        if isinstance(relation, Reading):
            continue
        level = session.level(rid)
        state = "ok" if relation.held else "no"
        out.append(
            f"P {rid} 0 {level} {DOOR.get(relation.kind, relation.kind)} {state} "
            f"{relation.label()}\t{relation.facts()}"
        )
    return out


def _facts(place: int, relation: Relation) -> list[str]:
    """What a visited card knows about itself; a ghost says nothing yet."""
    if not relation.held or not isinstance(relation, Reading):
        return []
    rules = relation.reader_text().count("::=") or len(
        relation.reader_text().split("\n")
    )
    out = [
        f"k {place} {len(relation.document())} {len(relation.spans)} {rules} "
        f"{relation.seconds:.2f} {1 if relation.faithful else 0} 0"
    ]
    texture = band(relation)
    if texture:
        out.append(f"b {place} " + " ".join(str(n) for n in texture))
    return out
