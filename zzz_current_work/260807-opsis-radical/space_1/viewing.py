"""The VIEWING relation — a value, looked at as what it IS.

An IR value is a DAG keyed by OBJECT IDENTITY, and that is the fact a string
rendering destroys: the authored metagrammar shares one quantifier nearly two
hundred times where a fresh parse of the same text shares nothing. So one
object reached N ways is ONE node with N edges arriving, and the sharing is
the picture.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from relate import KINDS, SUBJECT, Relation, Role, Thing, Value

__all__ = ["Node", "Viewing", "walk"]

CEILING = 4000


class Node:
    """One object in the value's graph, at the identity it was reached by."""

    __slots__ = ("kids", "payload", "place", "refs", "subtree", "tier", "type")

    def __init__(self, place: int, thing: object) -> None:
        self.place = place
        self.type = type(thing).__name__
        self.tier = tier(thing)
        self.kids = 0
        self.subtree = 1
        self.refs = 0
        self.payload = payload(thing)


def tier(node: object) -> str:
    """Which tier of the spine this sits on — the one thing a node cannot fake."""
    if isinstance(node, (str, int)) and not isinstance(node, tuple):
        return "scalar"
    if getattr(type(node), "_fields", ()):
        return "record"
    if isinstance(node, tuple):
        return "seq"
    return "leaf"


def payload(node: object) -> str:
    """A scalar IS its payload, so say it; a record's payload is its shape."""
    if isinstance(node, str):
        return str(node).replace("\n", "\\n")[:60]
    if isinstance(node, int) and not isinstance(node, tuple):
        return str(int(node))
    return ""


def kids_of(node: object) -> list[object]:
    """This node's children, however it happens to hold them.

    The engine's hot paths use bare tuple aliases beside the record tiers, so
    a value graph meets both. Neither is wrong; the walk takes what it finds.
    """
    # a record IS its field tuple, so read the tuple: children() filters to
    # the bound fields, and a filtered walk cannot see that one quantifier
    # object is the same object in two hundred places
    if isinstance(node, tuple):
        return list(node)
    ask = getattr(node, "children", None)
    kids = ask() if callable(ask) else ()
    return list(kids) if isinstance(kids, Sequence) else []


def labels(node: object) -> list[str]:
    """What the edges out of this node are CALLED — fields, or ordinals."""
    fields = getattr(type(node), "_fields", ())
    if fields:
        return list(fields)
    return [str(index) for index in range(len(kids_of(node)))]


def walk(root: object) -> tuple[list[Node], list[tuple[int, int, str]]]:
    """The value as a graph. Identity is the key, so sharing survives."""
    seen: dict[int, int] = {}
    nodes: list[Node] = []
    edges: list[tuple[int, int, str]] = []
    order: list[object] = []

    def place_of(thing: object) -> int:
        key = id(thing)
        if key in seen:
            nodes[seen[key]].refs += 1
            return seen[key]
        seen[key] = len(nodes)
        nodes.append(Node(len(nodes), thing))
        order.append(thing)
        return seen[key]

    place_of(root)
    at = 0
    while at < len(order) and len(nodes) < CEILING:
        thing = order[at]
        kids = kids_of(thing)
        names = labels(thing)
        nodes[at].kids = len(kids)
        for index, kid in enumerate(kids):
            label = names[index] if index < len(names) else str(index)
            edges.append((at, place_of(kid), label))
        at += 1
    _sizes(nodes, edges)
    return nodes, edges


def _sizes(nodes: list[Node], edges: list[tuple[int, int, str]]) -> None:
    """Subtree size, counted the honest way: a shared node is counted once."""
    out: dict[int, list[int]] = {}
    for frm, to, _ in edges:
        out.setdefault(frm, []).append(to)
    for node in reversed(nodes):
        reach = {node.place}
        stack = list(out.get(node.place, ()))
        while stack:
            here = stack.pop()
            if here in reach:
                continue
            reach.add(here)
            stack.extend(out.get(here, ()))
        node.subtree = len(reach)


class Viewing(Relation):
    """A value, standing as the subject of its own room."""

    kind = "viewing"
    slots = (SUBJECT,)

    def __init__(self, rid: str, cast: Mapping[str, Thing]) -> None:
        super().__init__(rid, cast)
        self.nodes: list[Node] = []
        self.edges: list[tuple[int, int, str]] = []

    @classmethod
    def licenses(cls, role: Role, thing: Thing) -> bool:
        """Anything that IS a value can be looked at as one."""
        return role is SUBJECT and isinstance(thing, Value)

    def label(self) -> str:
        return f"{self.cast[SUBJECT.name].name} — as IR"

    def hold(self) -> None:
        """Walk it once. The walk is the room."""
        if self.held:
            return
        self.held = True
        subject = self.cast[SUBJECT.name]
        if isinstance(subject, Value):
            self.nodes, self.edges = walk(subject.value)

    def facts(self) -> str:
        shared = sum(1 for node in self.nodes if node.refs)
        return (
            f"{len(self.nodes):,} nodes · {len(self.edges):,} edges · {shared} shared"
        )

    def frame(self) -> str:
        """The value's graph, in the leaf's own IR vocabulary."""
        return "\n".join(
            [
                f"root {self.cast[SUBJECT.name].name}",
                f"nodes {len(self.nodes)}",
                f"#NODES {len(self.nodes)}",
                *(
                    f"{n.place} {n.type} {n.tier} {n.kids} {n.subtree} {n.refs} 0"
                    f" {n.payload}"
                    for n in self.nodes
                ),
                f"#IREDGES {len(self.edges)}",
                *(f"{a} {b} {label}" for a, b, label in self.edges),
                "#KIDS 0",
                "",
            ]
        )

    def parts(self) -> Sequence[Thing]:
        return list(self.cast.values())


KINDS[Viewing.kind] = Viewing
