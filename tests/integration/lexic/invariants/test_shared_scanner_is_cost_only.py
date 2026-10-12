"""The shared scanner moves scan COST, never a plan's answer.

One scanner reads the union of every certified plan's mark spellings rather
than the grammar's every mark, so a stretch the cut search reads carries only
spellings some plan can cut at. That is only sound if the union changes what
each plan PAYS and not what it FINDS — otherwise plans stop being independent
and any table built by running them one at a time is measuring something the
orchestrator never does.

Two claims hold it up, both stated in `cuts.py`:

* the candidates keep only the plan's OWN spelling — the scanner reports
  marks of the union, and each plan keeps its own;
* the depth-carrying character sets (`openers` / `closers`) come from
  grammar-derived pairs, not from the union — "pairs come from the grammar,
  because depth does not belong to any one plan".
"""

from __future__ import annotations

import pytest

from lexic.parsing.parallel.plan.cuts import (
    Level,
    cut_offsets,
    reads_a_sweep,
    shared_scanner,
)
from lexic.parsing.parallel.planner import safe_plans, split_plans
from tools.benchmark.cases.grammars import BENCHES

WORKERS = 4


def sweeping(name: str):
    """A grammar's sweep-reading certified plans, or an empty tuple."""
    bench = next(one for one in BENCHES if one.name == name)
    grammar = bench.compiled.codegen_grammar
    plans = safe_plans(split_plans(grammar), grammar)
    return bench, grammar, tuple(one for one in plans if reads_a_sweep(one))


ROWS = [one.name for one in BENCHES]


@pytest.mark.parametrize("name", ROWS)
def test_the_union_does_not_change_what_a_plan_finds(name: str) -> None:
    """Each plan's candidates and cuts are the same under the shared scanner
    and its own.

    This is the independence the cascade table rests on: if a plan's answer
    moved when another plan joined the union, running plans one at a time
    would measure a different machine from the one that runs.
    """
    bench, grammar, plans = sweeping(name)
    if not plans:
        pytest.skip(f"{name} has no sweep-reading certified plan")
    shared = shared_scanner(grammar, plans)
    assert shared is not None, "plans read a sweep but no scanner was built"

    end = len(bench.full) + 1
    found = 0
    for plan in plans:
        alone = cut_offsets(plan, bench.full, WORKERS, Level(plan.scanner, bench.full))
        together = cut_offsets(plan, bench.full, WORKERS, Level(shared, bench.full))
        listed = list(together.marks(0, 0, end))
        found += len(listed)
        assert listed == list(alone.marks(0, 0, end)), f"{name}: {plan.owner} moved"
        assert together.offsets == alone.offsets, f"{name}: {plan.owner}'s cuts moved"
    assert found, f"{name}: no plan found a candidate — nothing was compared"


@pytest.mark.parametrize("name", ROWS)
def test_the_shared_scanners_pairs_come_from_the_grammar(name: str) -> None:
    """Depth accounting does not depend on which plans are in the union.

    Built twice — from every sweep-reading plan, and from one of them alone.
    The pairs must be identical, because they are the grammar's.
    """
    _bench, grammar, plans = sweeping(name)
    if len(plans) < 2:
        pytest.skip(f"{name} has fewer than two sweep-reading plans")

    everyone = shared_scanner(grammar, plans)
    just_one = shared_scanner(grammar, plans[:1])
    assert everyone is not None and just_one is not None

    assert everyone.openers == just_one.openers, "depth followed the plan set"
    assert everyone.closers == just_one.closers, "depth followed the plan set"


def test_at_least_one_grammar_actually_exercises_the_union() -> None:
    """The null rule: if no grammar has two sweep-reading plans, the tests
    above skip everywhere and pin nothing."""
    with_two = [name for name in ROWS if len(sweeping(name)[2]) >= 2]

    assert with_two, "no grammar exercises a shared sweep across plans"
