"""`field_children` counts a model the way a reader walks it.

The spine's stated child definition used to stop at a repeated field: a run is
a plain `tuple`, not an `IrSelf`, so a filter to `IrSelf` returned the run's
holder and nothing under it. A census of a csv document reported FOUR nodes.

Both directions are pinned here, because the fix could go wrong either way:

* over a MODEL it must now agree with an independent position walk — a second
  route that shares no code with it;
* over a GRAMMAR AST nothing may move, since no grammar node stores a bare
  tuple of nodes and the change must not have reached the spine.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.ir import IrNone, IrSelf
from lexic.ir.identity import field_children
from lexic.parsing.products import _model_product, pda_model
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES


def census(value: IrSelf) -> int:
    """Nodes reachable under the spine's stated child definition."""
    total = 0
    stack: list[IrSelf] = [value]
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(field_children(node))
    return total


def positions(value: object) -> int:
    """The same count by an independent route — descend every tuple.

    Shares no code with `field_children`: it descends containers and counts
    `IrSelf`, where that one filters and splices. Two instruments built for the
    same question from different directions, so agreement is evidence.
    """
    total = 0
    stack: list[object] = [value]
    while stack:
        node = stack.pop()
        if node is IrNone:
            continue
        if isinstance(node, IrSelf):
            total += 1
        if isinstance(node, tuple):
            stack.extend(node)
    return total


@pytest.mark.parametrize("name", ["csv", "nested", "gbnf-meta"])
def test_a_models_census_equals_its_position_count(name: str) -> None:
    """Over a built model the two routes agree to the unit."""
    bench = next(one for one in BENCHES if one.name == name)
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)
    model = pda_model(product.pda, bench.corpus, bench.compiled.product.executor)

    assert census(model) == positions(model)


def test_the_csv_census_is_its_whole_document_not_its_first_field() -> None:
    """The regression in one number, on the witness that exposed it.

    Four is what the filtering walk returned for this document: the root, its
    first row, and that row's first field. Everything past the first run was
    invisible.
    """
    bench = next(one for one in BENCHES if one.name == "csv")
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)
    model = pda_model(product.pda, bench.corpus, bench.compiled.product.executor)

    assert census(model) > 4, "the walk stopped at the first run again"


def bare_runs(value: object) -> list[str]:
    """Every part that the new branch would splice — empty on a grammar.

    Stated as the CONDITION rather than as a count: the grammar side is the
    reason this walk exists (the fold's rewrite reads it), and a change made
    for models must not reach it. A count would have to be written down, and a
    number in a test rots the moment a grammar gains a rule; "no node has one"
    holds however the corpus grows.
    """
    found: list[str] = []
    seen: set[int] = set()
    stack: list[object] = [value]
    while stack:
        node = stack.pop()
        if not isinstance(node, IrSelf) or id(node) in seen:
            continue
        seen.add(id(node))
        for part in tuple(node) if isinstance(node, tuple) else ():
            if isinstance(part, tuple) and part.__class__ is tuple and part:
                if all(isinstance(one, IrSelf) for one in part):
                    found.append(f"{type(node).__name__} holds a bare run")
        stack.extend(field_children(node))
    return found


@pytest.mark.parametrize("name", [one.name for one in BENCHES])
def test_no_grammar_node_holds_a_bare_run(name: str) -> None:
    """So the new branch is unreachable on the grammar side, by construction."""
    bench = next(one for one in BENCHES if one.name == name)

    assert not bare_runs(bench.compiled.codegen_grammar)


def test_no_ground_truth_grammar_holds_one_either() -> None:
    """The shipped corpus, by the same condition."""
    for path in sorted(GROUND_TRUTH.glob("*.gbnf")):
        assert not bare_runs(compile_from_path(path).codegen_grammar), path.name


def test_a_model_does_hold_one_so_the_condition_can_fail() -> None:
    """The control: the same probe finds runs where runs exist.

    Without it, "no grammar node holds a bare run" could be a probe that never
    fires rather than a fact about grammars.
    """
    bench = next(one for one in BENCHES if one.name == "csv")
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)
    model = pda_model(product.pda, bench.corpus, bench.compiled.product.executor)

    assert bare_runs(model), "the probe cannot see a run it is meant to find"
