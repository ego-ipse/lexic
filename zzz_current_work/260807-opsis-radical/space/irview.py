"""An IR value's OWN representation — not text, not a reading.

Recovered from the nuked `work/` prototype, whose finding stands: folding a
value onto a spelling shows only the spelling. The facts that make a value
what it IS do not survive the round trip:

- IDENTITY. One object reachable at many addresses is ONE object. The
  metagrammar's AST is ~830 unique nodes; ``IrQuantifier()`` is a single
  object referenced ~193 times, and every reference is re-spelled in the
  notation text. Here it is drawn once, with N edges arriving.
- TIER. A scalar IS its payload (no children — the payload belongs INSIDE
  the mark). A tuple is its positional children. A record is its NAMED
  fields, and the names are the edges.
- ABSENCE. ``IrNone`` is a value, not a blank.
- REFUSAL. ``IrLambda`` carries a callable, so the notation refuses it —
  the boundary of representability is part of the picture, not an error.

This module computes that structure. It never emits text for a value.
"""

from __future__ import annotations

import sys

from lexic.ir import IrNone, IrSelf

MAX_NODES = 8000


def tier_of(node: object) -> str:
    """Which tier of the spine this node sits on — how it must be drawn."""
    if node is IrNone:
        return "absence"
    if isinstance(node, dict):
        return "map"
    if isinstance(node, list):
        return "list"
    if isinstance(node, tuple) and getattr(type(node), "_fields", ()):
        return "record"
    if isinstance(node, tuple):
        return "tuple"
    if isinstance(node, (str, int)):
        return "scalar"
    return "leaf"


def escape(text: str) -> str:
    """A payload can BE a newline (``IrLiteral("\\n")``): control characters
    are shown, never emitted raw — the wire is line-oriented."""
    return (text.replace("\\", "\\\\").replace("\n", "\\n")
            .replace("\r", "\\r").replace("\t", "\\t"))


def payload_of(node: object) -> str:
    """The payload a scalar IS, spelled for display only (never re-parsed)."""
    if node is IrNone:
        return "IrNone"
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, str):
        return escape(str(node))
    if isinstance(node, int):
        return str(int(node))
    return ""


def labels_for(node: object, kids: list) -> list[str]:
    """Edge labels: FIELD NAMES for a record, indices for a tuple.

    A record's children are named — that is the difference between a record
    and a tuple, and the edge is where it shows.
    """
    names: list[str] = []
    for attr in ("_child_attrs", "_fields"):
        declared = list(getattr(type(node), attr, ()) or ())
        if declared and len(declared) <= len(kids):
            names = list(declared)
            break
    by_id = {id(value): name for name, value in named_parts(node)}
    while len(names) < len(kids):
        names.append(by_id.get(id(kids[len(names)]), str(len(names))))
    return names


def named_parts(node: object) -> list[tuple[str, object]]:
    """The IR-valued parts a record exposes beyond ``children()``.

    A flavour carries its self-grammar, reducer and escapes as ClassVars, so
    ``children()`` is empty and the object draws as a childless leaf — which
    is how the flavour's anatomy stayed invisible. Discovered generically
    (any attribute holding an ``IrSelf``), never by a type table.
    """
    parts = []
    for name in sorted(dir(type(node))):
        if name.startswith("_"):
            continue
        try:
            value = getattr(node, name)
        except Exception:  # a property may refuse; that is not our business
            continue
        if isinstance(value, IrSelf) and value is not node:
            parts.append((name, value))
    return parts


def children_of(node: object) -> list:
    """Structural children UNION the named IR parts — both, deduped.

    A flavour's ``children()`` is its dispatch pair (actions, default), so
    stopping there hid the anatomy the flavour also carries by name
    (grammar, reducer, escapes, core_rules).
    """
    kids: list = []
    walk = getattr(node, "children", None)
    if callable(walk):
        kids = list(walk())
    elif isinstance(node, dict):
        kids = list(node.values())
    elif isinstance(node, (list, tuple)) and not isinstance(node, str):
        kids = list(node)
    seen = {id(kid) for kid in kids}
    for _name, value in named_parts(node):
        if id(value) not in seen:
            seen.add(id(value))
            kids.append(value)
    return kids


def dag(root: object) -> tuple[list, list]:
    """The value as a DAG keyed by OBJECT IDENTITY, not by position.

    :returns: ``(nodes, edges)``; a node is ``[idx, type, tier, payload,
        kid_count, subtree, refs, refused]`` and an edge is ``[parent, child,
        label]``. A node reached twice is ONE node with two edges.
    """
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(100000)
    try:
        seen: dict[int, list] = {}
        nodes: list[list] = []
        edges: list[list] = []
        stack: list[tuple] = [(root, -1, "")]
        while stack:
            node, parent, label = stack.pop()
            found = seen.get(id(node))
            if found is not None:
                found[6] += 1
                if parent >= 0:
                    edges.append([parent, found[0], label])
                continue
            if len(nodes) >= MAX_NODES:
                continue
            kids = children_of(node)
            refused = type(node).__name__ == "IrLambda"
            rec = [len(nodes), type(node).__name__, tier_of(node),
                   payload_of(node) if not kids else "", len(kids), 1, 1,
                   1 if refused else 0]
            seen[id(node)] = rec
            nodes.append(rec)
            if parent >= 0:
                edges.append([parent, rec[0], label])
            for lab, kid in zip(labels_for(node, kids), kids):
                stack.append((kid, rec[0], lab))
        for parent, child, _lab in reversed(edges):
            nodes[parent][5] += nodes[child][5]
        return nodes, edges
    finally:
        sys.setrecursionlimit(old)


def node_at(root: object, path: str) -> object:
    """Resolve a child path (``"0/2/1"``) — the zoom address."""
    node = root
    for step in filter(None, path.split("/")):
        kids = children_of(node)
        index = int(step)
        if not 0 <= index < len(kids):
            return node
        node = kids[index]
    return node


def frame(root: object, path: str = "") -> str:
    """The wire form: identity, tiers, sharing, refusals — no spelling."""
    node = node_at(root, path)
    nodes, edges = dag(node)
    shared = [n for n in nodes if n[6] > 1]
    tiers: dict[str, int] = {}
    for entry in nodes:
        tiers[entry[2]] = tiers.get(entry[2], 0) + 1
    out = [
        f"type {type(node).__name__}",
        f"tier {tier_of(node)}",
        f"nodes {len(nodes)}",
        f"edges {len(edges)}",
        f"shared {len(shared)}",
        f"sharedrefs {sum(n[6] for n in shared)}",
        f"refused {sum(n[7] for n in nodes)}",
        f"tiers {' '.join(f'{k}:{v}' for k, v in sorted(tiers.items()))}",
        f"#NODES {len(nodes)}",
    ]
    out += [f"{n[0]} {n[1]} {n[2]} {n[4]} {n[5]} {n[6]} {n[7]} {n[3]}" for n in nodes]
    out.append(f"#IREDGES {len(edges)}")
    out += [f"{a} {b} {escape(str(lab))}" for a, b, lab in edges]
    kids = children_of(node)
    labels = labels_for(node, kids)
    out.append(f"#KIDS {len(kids)}")
    out += [f"{i} {labels[i]} {type(kid).__name__} {tier_of(kid)} "
            f"{len(children_of(kid))} {payload_of(kid) if not children_of(kid) else ''}"
            for i, kid in enumerate(kids)]
    return "\n".join(out) + "\n"
