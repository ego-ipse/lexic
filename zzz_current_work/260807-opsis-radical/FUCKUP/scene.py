"""A reading, spelled as the scene the leaf reads.

The leaf is kept as it stands — it earned its picture — so the adjustment is
on this side: what was hardcoded per fixture, the relation model answers. The
ladder is the strip DERIVED from the graph's edges, and the rule graph comes
from the reader's own AST rather than from anything declared here.
"""

from __future__ import annotations

import re

from lexic.ir import IrAst, IrRuleRef
from reading import Reading, turn
from relate import DOCUMENT, READER, Session

__all__ = ["ladder", "rule_graph", "ruledefs", "scene"]

HEAD = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")


def ruledefs(text: str) -> list[tuple[str, int, int]]:
    """Where each rule lives in the reader text — line ranges, addressable."""
    heads = [
        (match.group(1), index)
        for index, line in enumerate(text.split("\n"))
        if (match := HEAD.match(line))
    ]
    lines = text.count("\n")
    out = []
    for place, (name, start) in enumerate(heads):
        stop = heads[place + 1][1] - 1 if place + 1 < len(heads) else lines
        out.append((name, start, stop))
    return out


def rule_graph(ast: IrAst) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Reference edges and derivation distance from the start rule."""
    edges: list[tuple[str, str]] = []
    for rule in ast.rules:
        seen: set[str] = set()
        stack = [rule.body]
        while stack:
            node = stack.pop()
            if isinstance(node, IrRuleRef):
                name = str(node)
                if name not in seen:
                    seen.add(name)
                    edges.append((str(rule.name), name))
                continue
            stack.extend(node.children())
    out: dict[str, list[str]] = {}
    for frm, to in edges:
        out.setdefault(frm, []).append(to)
    return edges, _depths(ast, out)


def _depths(ast: IrAst, refs: dict[str, list[str]]) -> dict[str, int]:
    """BFS from the start rule; −1 for what the start never reaches."""
    start = str(ast.rules[0].name)
    depth = {str(rule.name): -1 for rule in ast.rules}
    depth[start] = 0
    frontier = [start]
    while frontier:
        onward = []
        for name in frontier:
            for ref in refs.get(name, []):
                if depth.get(ref, 0) == -1:
                    depth[ref] = depth[name] + 1
                    onward.append(ref)
        frontier = onward
    return depth


def as_written(rules: list[tuple[str, int, int]]) -> dict[str, str]:
    """Folded rule name → the spelling the reader text actually uses.

    Name folding is the engine's business, but the graph is drawn beside the
    TEXT: a node called ``json-text`` where the grammar says ``JSON-text``
    matches nothing, and the start rule — the layout's anchor — goes missing.
    """
    return {name.casefold(): name for name, _, _ in rules}


HOISTED = re.compile(r"^(.*)-(?:item|arm)\d*$")


def _said(written: dict[str, str], name: str) -> str:
    """This rule, spelled the way the grammar spells it.

    A codegen rule has no line of its own: ``<rule>-item[N]`` and
    ``<rule>-arm<N>`` are what the hoisting passes name the pieces they cut
    out of ``<rule>``, so an occurrence of one is an occurrence INSIDE that
    rule and lights its line. The inverse is the namer's own, not a guess.
    """
    said = written.get(name.casefold())
    if said is not None:
        return said
    cut = HOISTED.match(name)
    return _said(written, cut.group(1)) if cut else name


def ladder(session: Session, rid: str) -> list[str]:
    """The strip: every instance the session holds, focus lit.

    Derived from the graph each time it is asked. The leaf travels by the
    index of a rung, so this order is the same order the map uses.
    """
    session.expand()
    out = []
    for place, step in enumerate(session.relations):
        lit = 1 if step == rid else 0
        kind = "r" if session.relations[step].held else "x"
        out.append(f"{place} {lit} {kind} {session.relations[step].label()}")
    return out


def scene(session: Session, rid: str) -> str | None:
    """Everything the leaf needs to draw this reading, in its own vocabulary."""
    relation = session.relations.get(rid)
    if not isinstance(relation, Reading):
        return None
    reader_text = relation.reader_text()
    document = relation.document()
    rules = ruledefs(reader_text)
    written = as_written(rules)
    # a span names the rule that BUILT it, in the engine's folded spelling;
    # the reader shows the grammar's. Co-selection is a name match, so the
    # names have to be the same names — a generated rule keeps its own,
    # because there is no line in the text for it to light
    names = sorted({_said(written, span.rule) for span in relation.spans})
    fields = sorted({span.field for span in relation.spans})
    rule_at = {name: index for index, name in enumerate(names)}
    field_at = {name: index for index, name in enumerate(fields)}
    turned = turn(relation.cast[READER.name])
    edges, depth = rule_graph(turned.machine.grammar) if turned else ([], {})
    edges = [(_said(written, a), _said(written, b)) for a, b in edges]
    depth = {_said(written, name): at for name, at in depth.items()}
    rungs = ladder(session, rid)
    return "\n".join(
        [
            "#META",
            f"fixture {relation.label()}",
            f"reader {relation.cast[READER.name].name}",
            f"seconds {relation.seconds:.2f}",
            "resolver 0",
            f"faithful {1 if relation.faithful else 0}",
            "generation 1",
            "t 0.0",
            f"#POLICY {len(session.policy)}",
            *(f"{key} {value}" for key, value in session.policy.items()),
            f"#LADDER {len(rungs)}",
            *rungs,
            f"#RULEDEFS {len(rules)}",
            *(f"{name} {a} {b}" for name, a, b in rules),
            f"#RULENAMES {len(names)}",
            *names,
            f"#FIELDNAMES {len(fields)}",
            *fields,
            f"#EDGES {len(edges)}",
            *(f"{a} {b}" for a, b in edges),
            f"#DEPTHS {len(depth)}",
            *(f"{name} {d}" for name, d in depth.items()),
            f"#SPANS {len(relation.spans)}",
            *(
                f"{s.start} {s.end} {s.depth} {rule_at[_said(written, s.rule)]} "
                f"{field_at[s.field]}"
                for s in relation.spans
            ),
            f"#READER {len(reader_text)}",
            reader_text,
            f"#DOC {len(document)}",
            document,
            "",
        ]
    )


def document_of(session: Session, rid: str) -> str:
    """The text this reading is of — asked by the routes that edit it."""
    relation = session.relations.get(rid)
    return relation.cast[DOCUMENT.name].spelling() if relation else ""
