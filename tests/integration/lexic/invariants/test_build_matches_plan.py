"""Every composed build still agrees with the plan it was composed from.

``clone.build`` is composed from ``clone.plan`` once, at bake, and never
consulted again — so the two are a coupling with no runtime check behind it.
A later pass that rewrote ``plan`` after the bake would leave a builder
reading the old one and produce silently wrong records: same class, same
width, wrong values. The four writers all write both together today
(``product.bake_product_build``, ``flatten.clear_build``, ``lower``'s
attempt-sub copy), and this is what says so.

Two gates, deliberately different in kind. The corpus walk runs every clone
of every ground-truth grammar through a synthetic capture state and checks the
record against an independent reading of that clone's own plan. The static
check refuses a new writer of ``.plan`` that does not also write ``.build``,
which the walk cannot see because an un-baked pass leaves no trace in a
compiled artefact.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lexic.compile import compile_from_path
from lexic.parsing.pda.compiler.program.flatten import FlatClone, no_shape_build
from lexic.parsing.pda.compiler.program.opcodes import BUILD_DISPATCH
from lexic.parsing.pda.compiler.program.specialize import clone_arms
from lexic.parsing.products import pda_tables
from tests.build_tail_helpers import plan_means
from tests.paths import ABNF_GRAMMARS, GBNF_GRAMMARS, GROUND_TRUTH

NEEDS_VOCABULARY = frozenset({"think.gbnf"})
"""Grammars whose token terminals cannot concretize without a tokenizer.

Excluded because they cannot be COMPILED here at all, not because their
builders are exempt: a bound vocabulary is a fixture this gate does not need.
"""

PDA_SOURCES = (
    "src/lexic/parsing/pda/compiler/program/product.py",
    "src/lexic/parsing/pda/compiler/program/flatten.py",
    "src/lexic/parsing/pda/compiler/program/lower.py",
    "src/lexic/parsing/pda/compiler/program/specialize.py",
)
"""Every module that may write clone build state."""


def every_clone(node, seen: dict[int, FlatClone]) -> None:
    """Each clone of a compiled program, once, by identity."""
    if not isinstance(node, FlatClone) or id(node) in seen:
        return
    seen[id(node)] = node
    if node.mode == BUILD_DISPATCH:
        for _chars, _negated, target in node.selectors:
            every_clone(target, seen)
        every_clone(node.default, seen)
        return
    for arm in clone_arms(node):
        for payload in arm.payloads:
            every_clone(payload, seen)
    for entry in node.attempt[1] if node.attempt else ():
        every_clone(entry[-1], seen)


def capture_state(width: int):
    """A ``(text, ends, sinks)`` wide enough for any plan of ``width`` fields.

    The values are arbitrary and distinct — what matters is that reading the
    wrong item, or the wrong lane, cannot coincide with reading the right one.
    """
    return (
        "abcdefghijklmnopqrstuvwxyz",
        list(range(width + 2)),
        [[object()] for _ in range(width + 2)],
    )


@pytest.mark.parametrize(
    "name",
    [n for n in (*GBNF_GRAMMARS, *ABNF_GRAMMARS) if n not in NEEDS_VOCABULARY],
)
def test_every_clone_s_build_agrees_with_its_own_plan(name: str) -> None:
    """Across the whole corpus, no builder reads a plan other than its own."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    tables = pda_tables(compiled.codegen_grammar, compiled.product)
    seen: dict[int, FlatClone] = {}
    every_clone(tables.program.start, seen)

    checked = 0
    for clone in seen.values():
        if clone.build is no_shape_build or not clone.plan:
            continue
        width = max(item for _m, item, _lo, _d in clone.plan) + 1
        text, ends, sinks = capture_state(width)
        built = clone.build(text, ends, sinks)
        assert list(built) == plan_means(clone.plan, text, ends, sinks), (
            f"{name}: {clone.name} builds something its plan does not say"
        )
        checked += 1
    assert checked, f"{name} composed no builder — the walk proved nothing"


@pytest.mark.parametrize("path", PDA_SOURCES)
def test_a_writer_of_plan_also_writes_build(path: str) -> None:
    """``plan`` and ``build`` are written together or not at all.

    Static, because the failure this guards is a pass that rewrites ``plan``
    AFTER the bake — which leaves a consistent-looking artefact and shows up
    only as wrong values much later.
    """
    source = Path(path).read_text(encoding="utf-8")
    writes_plan = {
        at
        for at, line in enumerate(source.splitlines())
        if re.search(r"\.plan\s*=", line)
    }
    writes_build = {
        at
        for at, line in enumerate(source.splitlines())
        if re.search(r"\.build\s*=", line)
    }
    for at in sorted(writes_plan):
        near = range(at - 12, at + 13)
        assert any(other in near for other in writes_build), (
            f"{path}:{at + 1} writes .plan with no .build beside it — a builder "
            "composed from the old plan would silently outlive it"
        )
