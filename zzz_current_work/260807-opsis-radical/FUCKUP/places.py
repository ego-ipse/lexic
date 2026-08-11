"""A room, spelled — the frame for a relation that is not a reading.

Sections spell themselves, and the emitter never inspects a payload: a
section says its kind and how many lines it brought, and the leaf draws that
kind. A room with no sections is a bug that says so, rather than a blank.
"""

from __future__ import annotations

from collections.abc import Sequence

import machine
import rails as tracks
import scene
from lexic.ir import IrAst
from compiling import Compiling
from keeping import Keeping
from reading import Reading, turn
from relate import READER, SUBJECT, Relation, Session, Value
from viewing import Viewing

__all__ = ["Section", "frame", "sections"]


class Section:
    """One block of a room's frame: a kind, and the lines it brought."""

    def __init__(self, kind: str, body: Sequence[str]) -> None:
        self.kind = kind
        self.body = list(body)

    def wire(self) -> list[str]:
        return [f"#SEC {self.kind} {len(self.body)}", *self.body]


def _missing(session: Session, pid: str) -> str:
    """A miss is a ROOM that says so: an empty frame is how a blank happens."""
    known = ", ".join(session.relations) or "none"
    return (
        "\n".join(
            [
                f"#PLACE {pid} missing no such room",
                *Section("title", ["NO SUCH ROOM"]).wire(),
                *Section(
                    "refusal",
                    [f"nothing here is addressed {pid!r} — the session holds {known}"],
                ).wire(),
            ]
        )
        + "\n"
    )


def sections(relation: Relation) -> list[Section]:
    """What this room shows, DIVIDED INTO FACETS.

    A ``facet`` section opens one; everything after it belongs to it until the
    next. A room that spells none is one undivided pane with no seams and no
    doors — which is what "the new windows have no real facets" meant.
    """
    if isinstance(relation, Viewing):
        return _value_room(relation)
    if isinstance(relation, Compiling):
        return _machine_room(relation)
    if isinstance(relation, Keeping):
        return _artefact_room(relation)
    return [
        Section("facet", ["the cast — who is standing where"]),
        Section("title", [relation.label()]),
        Section(
            "kv", [f"{role}\t{thing.about()}" for role, thing in relation.cast.items()]
        ),
    ]


def _machine_room(relation: Compiling) -> list[Section]:
    """What the compiler made, and what it decided — its own words."""
    turned = turn(relation.cast[SUBJECT.name])
    said = machine.verdicts(turned.machine).splitlines()[1:] if turned else []
    rows: list[str] = []
    for row in said:
        parts = row.split(" ", 2)
        if len(parts) == 3 and parts[1].isdigit():
            rows.append(f"{parts[2]} — {parts[0]}")
    return [
        Section("facet", ["the machine — clones, not rules"]),
        Section(
            "kv",
            [
                f"clones\t{relation.clones}",
                f"rules\t{relation.rules}",
                *(
                    f"{kind}\t{count}"
                    for kind, count in sorted(relation.classes.items())
                ),
            ],
        ),
        Section("facet", ["what the compiler decided, per rule"]),
        Section("list", rows or ["nothing compiled"]),
    ]


def _artefact_room(relation: Keeping) -> list[Section]:
    """Every form this thing can be written as, each with its witness."""
    out: list[Section] = []
    for made in relation.artefacts:
        out.append(Section("facet", [f"{made.name} — {made.witness}"]))
        out.append(
            Section(
                "kv",
                [
                    f"chars\t{made.chars:,}",
                    f"witness\t{made.witness}",
                    f"words\t{made.words}",
                ],
            )
        )
        head = made.text.split("\n")[:60]
        out.append(Section("textlines", [f"|{line}" for line in head]))
    return out or [
        Section("facet", ["nothing to keep"]),
        Section("refusal", ["this thing has no artefact family — nothing compiles it"]),
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


def rule_room(session: Session, name: str) -> str | None:
    """One rule, as its own room — what it is, where it is used, how it reads.

    A rule IS a value, so this is a viewing like any other: the room is a
    relation instance, and it joins the graph rather than being a popup.
    """
    relation = session.relations.get(session.focus)
    if not isinstance(relation, Reading):
        return None
    turned = turn(relation.cast[READER.name])
    if turned is None:
        return None
    ast = turned.machine.grammar
    rule = next(
        (r for r in ast.rules if str(r.name).casefold() == name.casefold()), None
    )
    if rule is None:
        return None
    thing = Value(f"rule.{name}", name, rule)
    rid = session.enter("viewing", {SUBJECT.name: thing})
    out = [
        f"#PLACE rule.{name} rule {name} — a rule of {relation.cast[READER.name].name}"
    ]
    for section in _rule_facets(session, name, ast, rid, relation):
        out.extend(section.wire())
    return "\n".join(out) + "\n"


def _rule_facets(
    session: Session, name: str, ast: IrAst, rid: str, relation: Reading
) -> list[Section]:
    """What there is to know about one rule, each thing in its own facet."""
    used_by = [
        f"{frm} refers to it\tplace:rule.{frm}"
        for frm, to in scene.rule_graph(ast)[0]
        if to.casefold() == name.casefold()
    ]
    refs = [
        f"it refers to {to}\tplace:rule.{to}"
        for frm, to in scene.rule_graph(ast)[0]
        if frm.casefold() == name.casefold()
    ]
    here = [span for span in relation.spans if span.rule.casefold() == name.casefold()]
    verdict = _verdict_of(session, name)
    return [
        Section("facet", [f"{name} — as track"]),
        Section(
            "textlines",
            [f"|{line}" for line in tracks.rail(ast, name).splitlines()[1:]],
        ),
        Section("facet", ["what it is"]),
        Section(
            "kv",
            [
                f"verdict\t{verdict}",
                f"occurrences\t{len(here):,} in this document",
                f"first\t{here[0].start}..{here[0].end}" if here else "first\t—",
                f"depth\t{min((s.depth for s in here), default=0)}",
            ],
        ),
        Section("facet", ["what it touches"]),
        Section(
            "list",
            [*used_by, *refs] or ["nothing refers to it, and it refers to nothing"],
        ),
        Section("facet", ["as IR"]),
        Section("irvalue", [rid]),
    ]


def _verdict_of(session: Session, name: str) -> str:
    """What the compiler decided about this rule, in its own word."""
    relation = session.relations.get(session.focus)
    turned = turn(relation.cast[READER.name]) if isinstance(relation, Reading) else None
    if turned is None:
        return "unknown"
    for row in machine.verdicts(turned.machine).splitlines()[1:]:
        parts = row.split(" ", 2)
        if len(parts) == 3 and parts[2].casefold() == name.casefold():
            return parts[0]
    return "not a rule of the compiled machine"


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
    if pid.startswith("rule."):
        return rule_room(session, pid[5:]) or _missing(session, pid)
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
