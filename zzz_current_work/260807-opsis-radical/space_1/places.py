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
    """What this room shows. A relation kind that says nothing says so."""
    if isinstance(relation, Viewing):
        return [
            Section("title", [relation.label()]),
            Section(
                "kv",
                [
                    f"nodes\t{len(relation.nodes):,}",
                    f"edges\t{len(relation.edges):,}",
                    f"shared\t{sum(1 for n in relation.nodes if n.refs)}",
                ],
            ),
            Section("irvalue", [relation.rid]),
        ]
    return [
        Section("title", [relation.label()]),
        Section(
            "kv", [f"{role}\t{thing.about()}" for role, thing in relation.cast.items()]
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
    if pid == "index":
        return index(session)
    relation = session.relations.get(pid)
    if relation is None:
        return None
    relation.hold()
    out = [f"#PLACE {relation.rid} {relation.kind} {relation.label()}"]
    for section in sections(relation):
        out.extend(section.wire())
    return "\n".join(out) + "\n"
