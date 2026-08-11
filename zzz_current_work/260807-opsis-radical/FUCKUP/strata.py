"""The map between rooms — the relation graph, drawn.

A column is a THING, and the readings of that thing are its cards; a room
about that thing (its value, its machine, its artefacts) is a door under the
same column. An instance nobody has visited is a GHOST: it exists because the
engine licenses the cast that would make it, and travelling makes it real.

This is the graph the lineage strip is a 1-D projection of.
"""

from __future__ import annotations

from reading import Reading
from relate import DOCUMENT, READER, Relation, Session, Thing

__all__ = ["band", "cards", "frame", "lanes"]

BUCKETS = 44

# The leaf draws a door per room KIND it knows; a kind it has never heard of
# gets no door, so the mapping is stated rather than assumed.
DOOR = {"viewing": "value", "compiling": "compiler", "keeping": "artefacts"}


def cards(session: Session) -> list[str]:
    """Every relation instance, in index order — the address travel uses."""
    return list(session.relations)


def lanes(session: Session) -> tuple[dict[int, int], list[Thing]]:
    """Thing identity → column, and the things those columns are OF.

    A thing gets a column when a relation stands on it. The reader of one
    reading is the document of the next, so the columns come out as strata
    without anything storing a ladder.
    """
    # A COLUMN IS A THING SOMETHING WAS READ OF. Giving one to every thing in
    # any role put the instrument in two columns — its record and its grammar
    # — where it is one thing being read. A pure reader has no column: it is
    # the reader of the column it reads, and gets its own only when some
    # reading is OF it.
    order: list[Thing] = []
    at: dict[int, int] = {}
    for relation in session.relations.values():
        thing = relation.cast.get(DOCUMENT.name)
        if thing is not None and id(thing) not in at:
            at[id(thing)] = len(order)
            order.append(thing)
    for relation in session.relations.values():
        for thing in relation.cast.values():
            if id(thing) not in at:
                at[id(thing)] = _reads(session, thing, at)
    return at, order


def _reads(session: Session, thing: Thing, at: dict[int, int]) -> int:
    """The column of a thing that only ever reads: the one it reads."""
    for relation in session.relations.values():
        if relation.cast.get(READER.name) is thing:
            document = relation.cast.get(DOCUMENT.name)
            if document is not None and id(document) in at:
                return at[id(document)]
    return 0


def lane_of(session: Session, relation: Relation, at: dict[int, int]) -> int:
    """The column a room belongs under — the thing the room is about."""
    mine = {id(thing) for thing in relation.cast.values()}
    for thing in relation.cast.values():
        if id(thing) in at:
            return at[id(thing)]
    for other in session.relations.values():
        if any(id(product) in mine for product in other.products().values()):
            document = other.cast.get(DOCUMENT.name)
            if document is not None and id(document) in at:
                return at[id(document)]
    return 0


def band(relation: Relation) -> list[int]:
    """A card\'s own texture: how dense the parse is across the text."""
    if not isinstance(relation, Reading) or not relation.spans:
        return []
    chars = max(1, len(relation.document()))
    out = [0] * BUCKETS
    for span in relation.spans:
        out[min(BUCKETS - 1, (span.start * BUCKETS) // chars)] += 1
    top = max(out) or 1
    return [round(count * 100 / top) for count in out]


def frame(session: Session) -> str:
    """The map: columns of things, cards of readings, doors of rooms."""
    session.expand()
    order = cards(session)
    focus = order.index(session.focus) if session.focus in order else 0
    at, things = lanes(session)
    out = [f"#STRATA {len(order)} {focus}"]
    out.extend(f"L {lane} {thing.name}" for lane, thing in enumerate(things))
    rows: list[str] = []
    for place, rid in enumerate(order):
        relation = session.relations[rid]
        if isinstance(relation, Reading):
            rows.extend(_card(session, place, rid, relation, at))
        else:
            rows.append(_door(session, rid, relation, at))
    return "\n".join([*out, *rows]) + "\n"


def _card(
    session: Session,
    place: int,
    rid: str,
    relation: Reading,
    at: dict[int, int],
) -> list[str]:
    """One reading, under the column of the thing it reads."""
    lane = at.get(id(relation.cast[DOCUMENT.name]), 0)
    seen = 1 if relation.held else 0
    out = [f"c {place} {session.level(rid)} {lane} r {seen} {relation.label()}"]
    if not relation.held:
        return out
    rules = relation.reader_text().count("::=") or len(
        relation.reader_text().split("\n")
    )
    out.append(
        f"k {place} {len(relation.document())} {len(relation.spans)} {rules} "
        f"{relation.seconds:.2f} {1 if relation.faithful else 0} 0"
    )
    out.append(f"p {place} reduction = the model fold · vocabulary = char")
    texture = band(relation)
    if texture:
        out.append(f"b {place} " + " ".join(str(n) for n in texture))
    return out


def _door(session: Session, rid: str, relation: Relation, at: dict[int, int]) -> str:
    """One room, as a door under the column of the thing it is about."""
    kind = DOOR.get(relation.kind, relation.kind)
    state = "ok" if relation.held else "no"
    # an unvisited room has measured NOTHING: sending 0 clones reads as a fact
    # about the machine instead of a fact about the visit
    said = relation.facts() if relation.held else "not yet visited — travel builds it"
    return (
        f"P {rid} {lane_of(session, relation, at)} {session.level(rid)} "
        f"{kind} {state} {relation.label()}\t{said}"
    )
