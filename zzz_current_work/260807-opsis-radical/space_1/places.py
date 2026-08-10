"""A room, spelled — the frame for a relation that is not a reading.

Sections spell themselves, and the emitter never inspects a payload: a
section says its kind and how many lines it brought, and the leaf draws that
kind. A room with no sections is a bug that says so, rather than a blank.
"""

from __future__ import annotations

from collections.abc import Sequence

from relate import Relation, Session
from viewing import Viewing

__all__ = ["Section", "frame", "sections"]


class Section:
    """One block of a room's frame: a kind, and the lines it brought."""

    def __init__(self, kind: str, body: Sequence[str]) -> None:
        self.kind = kind
        self.body = list(body)

    def wire(self) -> list[str]:
        return [f"#SEC {self.kind} {len(self.body)}", *self.body]


def sections(relation: Relation) -> list[Section]:
    """What this room shows, DIVIDED INTO FACETS.

    A ``facet`` section opens one; everything after it belongs to it until the
    next. A room that spells none is one undivided pane with no seams and no
    doors — which is what "the new windows have no real facets" meant.
    """
    if isinstance(relation, Viewing):
        return _value_room(relation)
    return [
        Section("facet", ["the cast — who is standing where"]),
        Section("title", [relation.label()]),
        Section(
            "kv", [f"{role}\t{thing.about()}" for role, thing in relation.cast.items()]
        ),
    ]


def _value_room(relation: Viewing) -> list[Section]:
    """A value has more than one thing to say about itself, so it gets facets."""
    shared = [node for node in relation.nodes if node.refs]
    tiers: dict[str, int] = {}
    for node in relation.nodes:
        tiers[node.tier] = tiers.get(node.tier, 0) + 1
    return [
        Section("facet", ["the value — as IR"]),
        Section("irvalue", [relation.rid]),
        Section("facet", ["what it is"]),
        Section(
            "kv",
            [
                f"nodes\t{len(relation.nodes):,}",
                f"edges\t{len(relation.edges):,}",
                f"shared\t{len(shared)}",
                *(f"{tier}\t{count:,}" for tier, count in sorted(tiers.items())),
            ],
        ),
        Section("facet", ["what is SHARED — one object, reached many ways"]),
        Section(
            "list",
            [
                f"{node.type} — reached {node.refs + 1}x"
                + (f"  {node.payload}" if node.payload else "")
                for node in sorted(shared, key=lambda n: -n.refs)[:40]
            ]
            or ["nothing is shared — this value was built fresh, not authored"],
        ),
    ]


def index(session: Session) -> str:
    """Every room in the instrument, as doors — the one place that lists them."""
    rows = [
        f"{relation.label()}\tplace:{rid}"
        for rid, relation in session.relations.items()
        if relation.kind != "reading"
    ]
    out = ["#PLACE index rooms the rooms this session holds"]
    out.extend(Section("title", ["ROOMS"]).wire())
    out.extend(Section("list", rows or ["no rooms yet — a reading makes them"]).wire())
    return "\n".join(out) + "\n"


def frame(session: Session, pid: str) -> str | None:
    """The room by address, with everything it shows."""
    # any address may be asked for before the map was ever opened: the graph
    # grows on demand, or a room that exists reads as missing by accident
    session.expand()
    if pid == "index":
        return index(session)
    relation = session.relations.get(pid)
    if relation is None:
        # a miss is a ROOM that says so: a 404 leaves the leaf parsing an
        # empty body, and an empty frame is how a blank screen happens
        known = ", ".join(session.relations) or "none"
        return (
            "\n".join(
                [
                    f"#PLACE {pid} missing no such room",
                    *Section("title", ["NO SUCH ROOM"]).wire(),
                    *Section(
                        "refusal",
                        [
                            f"nothing here is addressed {pid!r} — the session holds {known}"
                        ],
                    ).wire(),
                ]
            )
            + "\n"
        )
    relation.hold()
    out = [f"#PLACE {relation.rid} {relation.kind} {relation.label()}"]
    for section in sections(relation):
        out.extend(section.wire())
    return "\n".join(out) + "\n"
