"""The compiled machine, as itself — clones, and what the compiler decided.

Nodes here are CLONES, not rules: the same rule compiled for two hard
continuations IS two nodes, and that multiplication is the machine. Every
fact is read back off the artifact the parse actually drives, so nothing here
can drift from what runs.
"""

from __future__ import annotations

from collections.abc import Sequence

from lexic.compile import CompiledGrammar
from lexic.parsing.pda.compiler.specs import (
    ArmSpec,
    CloneKey,
    CloneSpec,
    GroupSpec,
    IslandRef,
    ItemSpec,
)
from lexic.parsing.pda.compiler.tables import PdaTables

__all__ = ["automaton", "verdicts"]


def _refs(
    arms: Sequence[ArmSpec], default: Sequence[ItemSpec] | None
) -> list[CloneKey | IslandRef]:
    """Every clone or island an arm set can reach, groups included."""
    out: list[CloneKey | IslandRef] = []
    specs = [*(item for arm in arms for item in arm.specs), *(default or ())]
    while specs:
        item = specs.pop()
        if item.kind == "ref" and isinstance(item.payload, (CloneKey, IslandRef)):
            out.append(item.payload)
        elif item.kind == "grp" and isinstance(item.payload, GroupSpec):
            specs.extend(sub for arm in item.payload.arms for sub in arm.specs)
    return out


def _mode(spec: CloneSpec) -> str:
    """What kind of body this clone is — the shape the runtime walks."""
    if spec.match_only:
        return "value_str"
    if spec.attempt_follow is not None:
        return "alt"
    return "dispatch" if len(spec.arms) > 1 else "seq"


def _flags(spec: CloneSpec) -> str:
    """a attempt · l leaf · k k-window · p peek · s structured-noise."""
    out = ""
    out += "a" if spec.attempt_follow is not None else ""
    out += "l" if spec.match_only else ""
    out += "k" if any(arm.windows for arm in spec.arms) else ""
    out += "p" if any(arm.peek for arm in spec.arms) else ""
    out += "s" if spec.struct_arm is not None else ""
    return out or "-"


def automaton(tables: PdaTables) -> str:
    """The clone set, walked breadth-first from the start — depth is distance."""
    start = tables.start_key
    order: list[CloneKey] = []
    depth: dict[CloneKey, int] = {}
    if isinstance(start, CloneKey):
        order.append(start)
        depth[start] = 0
    at = 0
    edges: list[tuple[int, int]] = []
    while at < len(order):
        key = order[at]
        spec = tables.clones.get(key)
        if spec is not None:
            for target in _refs(spec.arms, spec.default):
                if isinstance(target, IslandRef) or target not in tables.clones:
                    continue
                if target not in depth:
                    depth[target] = depth[key] + 1
                    order.append(target)
                edges.append((at, order.index(target)))
        at += 1
    names = sorted({key.name for key in order})
    at_name = {name: index for index, name in enumerate(names)}
    rows = [
        f"{at_name[key.name]} {_mode(tables.clones[key])} "
        f"{_flags(tables.clones[key])} {depth[key]}"
        for key in order
        if key in tables.clones
    ]
    return "\n".join(
        [
            f"#ACLONES {len(rows)}",
            *rows,
            f"#ANAMES {len(names)}",
            *names,
            f"#AEDGES {len(edges)}",
            *(f"{a} {b}" for a, b in edges),
            "",
        ]
    )


def verdicts(compiled: CompiledGrammar) -> str:
    """Per rule, what the compiler decided — read off the artifact, in words.

    Silence IS the deterministic verdict: a rule with a single-pass body says
    ``predictive`` and carries no notes.
    """
    tables = compiled.pda_tables()
    islands = set(tables.island_follow)
    by_rule: dict[str, list[CloneSpec]] = {}
    for key, spec in tables.clones.items():
        by_rule.setdefault(key.name, []).append(spec)
    rows: list[str] = []
    for name in sorted({*by_rule, *islands}):
        kind, notes = _verdict(name, by_rule.get(name, []), islands)
        rows.append(f"{kind} {len(notes)} {name}")
        rows.extend(notes)
    return f"#VERDICTS {len({*by_rule, *islands})}\n" + "\n".join([*rows, ""])


def _verdict(
    name: str, specs: Sequence[CloneSpec], islands: set[str]
) -> tuple[str, list[str]]:
    """One rule's class and the notes that justify it."""
    if name in islands:
        return "island", ["a windowed Earley sub-parse decides this rule"]
    notes: list[str] = []
    if len(specs) > 1:
        notes.append(f"{len(specs)} clones — one per hard continuation")
    if any(spec.attempt_follow is not None for spec in specs):
        notes.append("ordered attempts with rollback decide the arms")
        return "attempt", notes
    gated = [flag for spec in specs for flag in _flags(spec) if flag in "kps"]
    if gated:
        notes.append("demoted to stored gates: " + ", ".join(sorted(set(gated))))
        return "gated", notes
    return "predictive", notes
