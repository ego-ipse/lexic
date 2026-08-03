"""The compile, stage by stage — and the module it ends at.

A stage is a diff, not a dump. What it added, what it rewrote shown
before and after, and how much it left alone: a pass that changed
nothing says so, and a pass this compile never ran is drawn as the
absence it is rather than omitted.

The module window is the same story's end — the importable twin the
grammar would export, derived from the grammar and never the other way
round.
"""

from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple, Sequence

from lexic.compile import CompiledGrammar, export_source
from lexic.grammars import get_flavour
from lexic.ir import IrAst, IrDoc
from opsis.opsis.draw.canvas import el
from opsis.opsis.draw.space import Box, Frame, frame
from opsis.opsis.read.views import Node, graph, panel

__all__ = ["Diff", "module_view", "pipeline_view"]

# ── the compile, stage by stage ───────────────────────────────────────


def pipeline_view(stages: Sequence[tuple[str, IrAst | None, str]]) -> IrDoc:
    """The compile as stages, each opening what IT changed.

    A stage is a diff, not a dump: what it added, what it rewrote shown
    before and after, and how much it left alone. A stage that does not
    occur in this compile is drawn as the absence it is.
    """
    nodes: list[Node] = []
    edges: list[tuple[int, int]] = []
    details: list[IrDoc] = []
    before: IrAst | None = None
    before_name = ""
    for column, (name, ast, why) in enumerate(stages):
        if ast is None:
            nodes.append(
                Node(
                    f"st-{name}",
                    f"{name} · not here",
                    column,
                    0,
                    "dim",
                    "",
                    f"st-{name}",
                )
            )
            details.append(_stage(Diff(name, why, [], [], 0, before_name)))
        else:
            added, changed = _diff(before, ast)
            mark = f"{name} · {len(list(ast.rules))} rules"
            if before is not None:
                mark += f" · +{len(added)} ~{len(changed)}"
            hue = (
                "amber"
                if before is None
                else ("green" if not (added or changed) else "cyan")
            )
            nodes.append(Node(f"st-{name}", mark, column, 0, hue, "", f"st-{name}"))
            details.append(
                _stage(
                    Diff(
                        name,
                        why,
                        added,
                        changed,
                        len(list(ast.rules)) - len(added) - len(changed),
                        before_name,
                    )
                )
            )
            before, before_name = ast, name
        if column:
            edges.append((column - 1, column))
    return panel(
        "each stage is what the one before it became · +added ~rewritten",
        graph(nodes, edges),
        *details,
    )


def _diff(
    before: IrAst | None, after: IrAst
) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Which rules a stage added, and which it rewrote — with their text."""
    if before is None:
        return [], []
    spell = get_flavour("gbnf")
    was = {str(rule.name): rule for rule in before.rules}
    added: list[tuple[str, str]] = []
    changed: list[tuple[str, str, str]] = []
    for rule in after.rules:
        name = str(rule.name)
        older = was.get(name)
        if older is None:
            added.append((name, str(spell.apply(rule, None))))
        elif repr(older.body) != repr(rule.body):
            changed.append(
                (name, str(spell.apply(older, None)), str(spell.apply(rule, None)))
            )
    return added, changed


class Diff(NamedTuple):
    """What one compile stage did — added, rewrote, and left alone."""

    name: str
    why: str
    added: list[tuple[str, str]]
    changed: list[tuple[str, str, str]]
    untouched: int
    before: str


def _stage(step: Diff) -> IrDoc:
    """One stage's own window — what it did, rule by rule."""
    name, before = step.name, step.before
    added, changed, untouched = step.added, step.changed, step.untouched
    rows: list[IrDoc] = [el("div", {"class": "note"}, step.why)]
    if not before:
        rows.append(
            el("div", {"class": "note"}, "the first stage — nothing precedes it")
        )
    elif not added and not changed:
        rows.append(el("div", {"class": "note"}, f"changed nothing from {before}"))
    for rule, source in added:
        rows.append(
            el(
                "div",
                {"class": "row added"},
                el("span", {"class": "name", "data-rule": rule}, f"+ {rule}"),
                el("pre", {"class": "src"}, source),
            )
        )
    for rule, was, now in changed:
        rows.append(
            el(
                "div",
                {"class": "row changed"},
                el("span", {"class": "name", "data-rule": rule}, f"~ {rule}"),
                el("pre", {"class": "src was"}, was),
                el("pre", {"class": "src"}, now),
            )
        )
    if untouched and before:
        rows.append(el("div", {"class": "note"}, f"{untouched} rules untouched"))
    return frame(
        Frame(
            f"st-{name}",
            f"{name} — what it changed",
            Box(24, 76, 560, 270),
            shown=False,
            sub=True,
        ),
        *rows,
    )


def module_view(compiled: CompiledGrammar, surface: str) -> IrDoc:
    """The importable twin this grammar would export.

    The grammar is the ground truth; a module is one way of writing it
    down, and its docstrings must be spelled in SOME surface. A grammar
    born from IR names none of its own, so one is chosen and said out
    loud — nothing is recompiled for it, only the label the exporter
    spells with.
    """
    artefact = compiled
    note = f"what export_module writes for {compiled.flavour}"
    if compiled.flavour != surface:
        artefact = replace(compiled, flavour=surface)
        note = (
            f"this grammar came from {compiled.flavour}, which spells no "
            f"surface of its own — its module is written out in {surface}"
        )
    source = export_source(artefact)
    return panel(
        f"{len(source.splitlines())} lines · {note} · "
        "derived from the grammar, never the other way round",
        el("pre", {"class": "src"}, source),
    )


# ── the registry: a product with no view is a DRAWN refusal ───────────
