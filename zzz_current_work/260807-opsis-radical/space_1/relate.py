"""Things, roles, relations, and the graph they form.

A thing is an object the session can point at. A role is a position in a
relation, never a type of object — json.gbnf is reader of one relation and
document of another at the same time. A relation instance is things standing
in roles plus what holding them produced, and the session is the graph of
those instances, edged by the casts that made them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from facets import Facet, Rows
from lexic.ir.spine.spine import IrSelf
from lexic.model import GrammarModel

__all__ = [
    "DOCUMENT",
    "FLAVOUR",
    "KINDS",
    "READER",
    "Relation",
    "Role",
    "SUBJECT",
    "Session",
    "Text",
    "Thing",
    "Value",
]


class Role:
    """One slot of a relation, addressed on the wire by name."""

    def __init__(self, name: str, means: str) -> None:
        self.name = name
        self.means = means

    def __repr__(self) -> str:
        return f"Role({self.name!r})"


READER = Role("reader", "the one whose grammar licenses the other")
DOCUMENT = Role("document", "the one being read")
SUBJECT = Role("subject", "the value this relation is of")
FLAVOUR = Role("flavour", "the spelling a value is emitted through")


class Thing:
    """An object a relation can cast into a role."""

    kind: str = "thing"

    def __init__(self, tid: str, name: str) -> None:
        self.tid = tid
        self.name = name

    def spelling(self) -> str:
        """This thing as characters, or ``""`` when it has none of its own."""
        return ""

    def about(self) -> str:
        """One line naming what this is."""
        return self.name


class Text(Thing):
    """Characters, and the file they came from when they came from one."""

    kind = "text"

    def __init__(
        self, tid: str, name: str, text: str, path: Path | None = None
    ) -> None:
        super().__init__(tid, name)
        self.text = text
        self.path = path

    def spelling(self) -> str:
        return self.text

    def about(self) -> str:
        return f"{self.name} — {len(self.text):,} chars"


class Value(Thing):
    """An ``IrSelf``: a grammar AST, a model, a flavour, or a node inside one."""

    kind = "value"

    def __init__(self, tid: str, name: str, value: IrSelf) -> None:
        super().__init__(tid, name)
        self.value = value

    def spelling(self) -> str:
        """A model spells itself; a bare value refuses — that asks a flavour."""
        if isinstance(self.value, GrammarModel):
            return self.value.to_text()
        return ""

    def about(self) -> str:
        return f"{self.name} — {type(self.value).__name__}"


KINDS: dict[str, type[Relation]] = {}


class Relation:
    """Things standing in roles. The room IS this; facets are facets of it."""

    kind: str = "relation"
    slots: tuple[Role, ...] = ()

    def __init__(self, rid: str, cast: Mapping[str, Thing]) -> None:
        self.rid = rid
        self.cast = dict(cast)
        self.held = False

    @classmethod
    def licenses(cls, role: Role, thing: Thing) -> bool:
        """Whether this thing may stand there — asked of the engine, never listed."""
        raise NotImplementedError(f"{cls.__name__} does not say what it licenses")

    @classmethod
    def complete(cls, cast: Mapping[str, Thing]) -> Mapping[str, Thing] | None:
        """Fill the slots a cast did not name, or refuse."""
        missing = [role.name for role in cls.slots if role.name not in cast]
        return None if missing else cast

    def hold(self) -> None:
        """Do the work the relation is. Idempotent; run on first focus."""
        raise NotImplementedError(f"{type(self).__name__} does not hold")

    def products(self) -> Mapping[str, Thing]:
        """What holding produced — things in their own right, castable onward."""
        return {}

    def label(self) -> str:
        """How this relation names itself, in one line."""
        return " ".join(thing.name for thing in self.cast.values())

    def parts(self) -> Sequence[Thing]:
        """Everything visible here: what you can see is what you can cast."""
        return [*self.cast.values(), *self.products().values()]

    def facets(self) -> Sequence[Facet]:
        """What this relation shows. The default says what it holds, plainly."""
        pairs = [(role, thing.about()) for role, thing in self.cast.items()]
        return [Rows("cast", "the cast", "who is standing where", pairs)]

    def arrangement(self, count: int) -> str:
        """Where the facets go, as a value the room authors — never a layout."""
        if count < 2:
            return "0"
        tree = str(count - 1)
        for index in range(count - 2, 0, -1):
            tree = f"(v {round(1 / (count - index), 3)} {index} {tree})"
        return f"(h 0.34 0 {tree})"

    def verdict(self) -> str:
        """What was checked here, and what it said. Empty when nothing was."""
        return ""

    def frame(self) -> list[str]:
        """This relation, spelled — the same discipline its facets follow."""
        shown = list(self.facets())
        out = [
            f"#ROOM {self.rid} {self.kind} {self.label()}",
            f"#ARRANGE {self.arrangement(len(shown))}",
        ]
        if self.verdict():
            out.append(f"#VERDICT {self.verdict()}")
        for facet in shown:
            out.extend(facet.wire())
        return out

    def facet(self, name: str) -> Facet | None:
        """The facet that owns an ask, by name."""
        return next((f for f in self.facets() if f.name == name), None)


class Edge:
    """A cast that happened: a thing, from one relation, into a role of another."""

    __slots__ = ("frm", "role", "tid", "to")

    def __init__(self, frm: str, tid: str, to: str, role: str) -> None:
        self.frm = frm
        self.tid = tid
        self.to = to
        self.role = role


class Offer:
    """A cast that WOULD be licensed from where you stand."""

    __slots__ = ("kind", "role", "thing")

    def __init__(self, thing: Thing, kind: str, role: Role) -> None:
        self.thing = thing
        self.kind = kind
        self.role = role


class Session:
    """Every relation the session holds, and how it got there."""

    def __init__(self) -> None:
        self.relations: dict[str, Relation] = {}
        self.edges: list[Edge] = []
        self.focus = ""
        self.made = 0
        # presentation state: the leaves interpret it, the instrument only
        # holds it, and a gesture in one leaf reaches the other through it
        self.policy: dict[str, str] = {}

    def enter(self, kind: str, cast: Mapping[str, Thing]) -> str:
        """Hold this relation (or find the one already holding it) and focus it."""
        rid = self.find(kind, cast)
        if rid is None:
            self.made += 1
            rid = f"{kind[0]}{self.made}"
            relation = KINDS[kind](rid, cast)
            relation.hold()
            self.relations[rid] = relation
        self.focus = rid
        return rid

    def find(self, kind: str, cast: Mapping[str, Thing]) -> str | None:
        """The instance already standing for this cast — the graph's identity."""
        for rid, relation in self.relations.items():
            same = relation.kind == kind and relation.cast.keys() == cast.keys()
            if same and all(relation.cast[k] is v for k, v in cast.items()):
                return rid
        return None

    def offers(self, rid: str) -> list[Offer]:
        """Every licensed cast from here — computed by asking, never listed."""
        out: list[Offer] = []
        for thing in self.relations[rid].parts():
            out.extend(self._for(thing))
        return out

    def _for(self, thing: Thing) -> list[Offer]:
        """What this one thing is licensed to become."""
        out: list[Offer] = []
        for name, kind in KINDS.items():
            licensed = [role for role in kind.slots if kind.licenses(role, thing)]
            out.extend(Offer(thing, name, role) for role in licensed)
        return out

    def moves(self, rid: str) -> list[Offer]:
        """The casts from here that would reach somewhere new.

        A move whose thing already stands in that role in some relation is not
        a move: entering would land on the instance already held. Identity is
        the object, never its name — two things may be called the same.
        """
        held = {
            (relation.kind, role, id(thing))
            for relation in self.relations.values()
            for role, thing in relation.cast.items()
        }
        return [
            offer
            for offer in self.offers(rid)
            if (offer.kind, offer.role.name, id(offer.thing)) not in held
        ]

    def cast(self, frm: str, tid: str, kind: str, role: str) -> str | None:
        """The one gesture: a visible thing, into a role, of a relation kind."""
        thing = self.visible(frm, tid)
        if thing is None or kind not in KINDS:
            return None
        made = KINDS[kind]
        slot = next((r for r in made.slots if r.name == role), None)
        if slot is None or not made.licenses(slot, thing):
            return None
        cast = made.complete({role: thing})
        if cast is None:
            return None
        to = self.enter(kind, cast)
        self.edges.append(Edge(frm, tid, to, role))
        return to

    def visible(self, rid: str, tid: str) -> Thing | None:
        """What you can see is what you can cast — nothing else is reachable."""
        relation = self.relations.get(rid)
        if relation is None:
            return None
        return next((t for t in relation.parts() if t.tid == tid), None)

    def frame(self, rid: str) -> str | None:
        """The room, and how it was reached, and where it can go from here.

        The session adds only what it alone knows — the strip and the licensed
        casts. The relation spells itself; the facets spell themselves.
        """
        relation = self.relations.get(rid)
        if relation is None:
            return None
        out = relation.frame()[:2]
        for step in self.strip(rid):
            state = "on" if step == rid else "off"
            out.append(f"#RUNG {step} {state} {self.relations[step].label()}")
        out += [
            f"#CAST {offer.thing.tid} {offer.kind} {offer.role.name} {offer.thing.name}"
            for offer in self.offers(rid)
        ]
        out.extend(relation.frame()[2:])
        return "\n".join(out) + "\n"

    def ask(self, query: Mapping[str, str]) -> str | None:
        """Route one ask to the facet that owns it. Nothing here knows kinds."""
        relation = self.relations.get(query.get("room", ""))
        if relation is None:
            return None
        facet = relation.facet(query.get("facet", ""))
        return None if facet is None else facet.ask(query)

    def strip(self, rid: str) -> Sequence[str]:
        """The lineage strip: DERIVED from the edges, never stored as a list.

        This is the seam the ruling named — an ordered list with an index
        cannot say that a relation was reached two ways, and the graph can.
        """
        path = [rid]
        seen = {rid}
        at = rid
        while True:
            back = next((edge.frm for edge in self.edges if edge.to == at), "")
            if not back or back in seen:
                return list(reversed(path))
            path.append(back)
            seen.add(back)
            at = back
