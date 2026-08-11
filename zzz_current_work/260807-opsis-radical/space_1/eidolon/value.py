"""A value drawn as what it IS — the spine's own shape, not a repr.

This is the surface the instrument exists for. Everything else here shows a
grammar doing something; this shows what a grammar IS once it is loaded: a
graph of `IrSelf` objects with four properties a string can never carry.

- **Identity.** One object reached from four places is ONE node with four
  edges arriving, not four copies. A repr shows four.
- **Tier.** A scalar IS its payload, a record IS its field tuple, and a
  record's edges are its FIELD NAMES. The tier is why `leaf == "x"` works.
- **Absence.** `IrNone` is a value with a place in the graph, never a hole.
- **Refusal.** A node the notation cannot spell (one carrying a callable) is
  part of the picture — the boundary is a fact about the value.

Reachability is by `__iter__`/fields, so a node type nobody here has heard of
is walked the same as any other — no isinstance ladder decides what is a node.
"""

from __future__ import annotations

from lexic.ir import IrNone
from lexic.ir.action.mapping import IrMapping
from lexic.ir.spine.records import IrNamedTuple, IrSeq, IrTuple
from lexic.ir.spine.scalars import IrChr, IrInt, IrStr
from lexic.ir.spine.spine import IrSelf

__all__ = ["Walk", "flat", "graph", "spell", "tier", "wire"]

# how deep a subtree count is worth walking before the number stops being
# information — the surface zooms, so nothing is lost by stopping
CEILING = 4096


def tier(node: IrSelf) -> str:
    """Which tier this node sits in — the leaf colours by it."""
    if node is IrNone:
        return "absence"
    if isinstance(node, (IrStr, IrInt, IrChr)):
        return "scalar"
    if isinstance(node, IrNamedTuple):
        return "record"
    if isinstance(node, (IrSeq, IrTuple)):
        return "tuple"
    return "map" if isinstance(node, IrMapping) else "record"


def edges_of(node: IrSelf) -> list[tuple[str, IrSelf]]:
    """This node's children, each under the name the node calls it.

    A record's children are its FIELDS — that name is the edge, and losing it
    is how an IR picture becomes an anonymous tree. A sequence's children are
    its indices, which are names too, just numeric ones.
    """
    # a map's edge name is its KEY: an action table read as an anonymous list
    # of bodies loses the only thing that says which construct each body is
    # for, which is most of what a dispatch table means
    if isinstance(node, IrMapping):
        return [
            (spell(key) or "«empty»", value)
            for key, value in zip(node.keys(), node.values())
            if isinstance(value, IrSelf)
        ]
    named = getattr(type(node), "_fields", ())
    if isinstance(node, IrNamedTuple) and named:
        return [
            (name, child)
            for name, child in zip(named, tuple(node))
            if isinstance(child, IrSelf)
        ]
    if isinstance(node, (IrSeq, IrTuple)) and not isinstance(node, IrNamedTuple):
        return [
            (str(i), child)
            for i, child in enumerate(tuple(node))
            if isinstance(child, IrSelf)
        ]
    return []


def flat(said: str) -> str:
    """One line of it. A value whose payload IS a newline breaks a
    line-oriented wire — the reducer's own literals do, and the surface drew
    an empty tree beside a correct header because every row after the first
    literal was off by one.
    """
    return (
        said.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def spell(part: object) -> str:
    """What a non-node field is CALLED. A class has a name; the notation
    spells that name, so ``<class 'lexic.ir.spine.scalars.IrChr'>`` is a repr
    leaking through where ``IrChr`` is the fact.
    """
    return part.__name__ if isinstance(part, type) else flat(str(part))


def payload_of(node: IrSelf) -> str:
    """What a node IS, spelled on one line — never a repr of the object.

    A record's PRIMITIVE fields are payload too. Only node-valued fields
    become edges, so a record whose fields are plain ints drew as an empty
    row — ``IrQuantifier`` showed nothing at all, when its whole content is
    the bound it carries.
    """
    if node is IrNone:
        return "IrNone — absence is a value"
    if isinstance(node, IrChr):
        return f"{int(node)} · {chr(int(node))!r}"
    if isinstance(node, (IrStr, IrInt)):
        said = flat(str(node))
        return said if len(said) <= 90 else said[:87] + "…"
    named = getattr(type(node), "_fields", ())
    if isinstance(node, IrNamedTuple) and named:
        plain = [
            f"{name}={spell(part)}"
            for name, part in zip(named, tuple(node))
            # a class IS the content of an IrBuild — dropping it as "callable"
            # left the row that says WHAT IS BUILT completely blank
            if not isinstance(part, IrSelf)
            and (isinstance(part, type) or not callable(part))
        ]
        return " · ".join(plain)[:90]
    return ""


def refused(node: IrSelf) -> bool:
    """Does this node carry something the notation cannot spell back?

    A plain ``callable()`` test says yes to almost everything: an IR node IS
    an action, so nodes are callable by construction, and a class held by
    ``IrBuild`` is callable too — but a class has a NAME, and the notation
    spells names. What no text can carry is a function: a lambda or a bound
    method riding inside a value. That, and only that, is the boundary.
    """
    if not isinstance(node, IrTuple):
        return False
    return any(
        callable(part) and not isinstance(part, (IrSelf, type)) for part in tuple(node)
    )


class Walk:
    """One traversal: unique nodes, the edges between them, how often reached."""

    __slots__ = ("at", "edges", "nodes", "refs", "subtree")

    def __init__(self) -> None:
        self.nodes: list[IrSelf] = []
        self.at: dict[int, int] = {}
        self.edges: list[tuple[int, int, str]] = []
        self.refs: dict[int, int] = {}
        self.subtree: dict[int, int] = {}

    def index(self, node: IrSelf) -> int:
        """This node's number — the SAME number every time it is reached."""
        seen = self.at.get(id(node))
        if seen is not None:
            self.refs[seen] += 1
            return seen
        at = len(self.nodes)
        self.at[id(node)] = at
        self.nodes.append(node)
        self.refs[at] = 1
        return at

    def walk(self, node: IrSelf) -> int:
        """Number this node and everything under it, once each."""
        first = id(node) not in self.at
        at = self.index(node)
        if not first:
            return at
        total = 1
        for name, child in edges_of(node):
            self.edges.append((at, self.walk(child), name))
            total += self.subtree.get(self.at[id(child)], 1)
            if total > CEILING:
                break
        self.subtree[at] = total
        return at


def descend(root: IrSelf, path: str) -> tuple[IrSelf, list[str]]:
    """Follow a path of child indices — the trail is what was entered."""
    node = root
    trail: list[str] = []
    for step in filter(None, path.split("/")):
        kids = edges_of(node)
        if not step.isdigit() or int(step) >= len(kids):
            break
        trail.append(type(node).__name__)
        node = kids[int(step)][1]
    return node, trail


def graph(root: IrSelf, path: str = "") -> Walk:
    """The graph under this value, entered at ``path``."""
    node, _ = descend(root, path)
    walk = Walk()
    walk.walk(node)
    return walk


def wire(root: IrSelf, path: str = "") -> str:
    """The value as the leaf reads it — nodes, edges, and the root's children."""
    node, _ = descend(root, path)
    walk = graph(root, path)
    shared = [at for at, count in walk.refs.items() if count > 1]
    tiers = sorted({tier(n) for n in walk.nodes})
    kids = edges_of(node)
    return "\n".join(
        [
            f"type {type(node).__name__}",
            f"tier {tier(node)}",
            f"nodes {len(walk.nodes)}",
            f"edges {len(walk.edges)}",
            f"shared {len(shared)}",
            f"sharedrefs {sum(walk.refs[at] for at in shared)}",
            f"refused {sum(1 for n in walk.nodes if refused(n))}",
            f"tiers {' '.join(tiers)}",
            f"#NODES {len(walk.nodes)}",
            *(
                f"{at} {type(n).__name__} {tier(n)} {len(edges_of(n))} "
                f"{walk.subtree.get(at, 1)} {walk.refs[at]} "
                f"{1 if refused(n) else 0} {payload_of(n)}"
                for at, n in enumerate(walk.nodes)
            ),
            f"#IREDGES {len(walk.edges)}",
            *(f"{a} {b} {label}" for a, b, label in walk.edges),
            f"#KIDS {len(kids)}",
            *(
                f"{i} {label} {type(child).__name__} {tier(child)} "
                f"{len(edges_of(child))} {payload_of(child)}"
                for i, (label, child) in enumerate(kids)
            ),
            "",
        ]
    )
