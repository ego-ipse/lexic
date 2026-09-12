"""Selecting cuts once yields exactly what selecting them per plan yielded.

The depth-0 rebase is a prefix sum over the scan windows' own deltas and reads
nothing of the scanner that produced them, so every certified plan reading one
sweep was recomputing the same list before applying its own filter to it. It is
now computed once and shared; each plan still filters it.

That is an optimisation, so the only acceptable evidence is that the offsets do
not move: for every plan kind a grammar certifies, over every bench grammar and
both ground-truth json formulations, the cuts chosen from the shared rebase are
the cuts chosen from a rebase the plan computed alone.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path
from lexic.parsing.parallel.orchestrate import _safe_plans, _split_plans
from lexic.parsing.parallel.plan.cuts import (
    cut_offsets,
    reads_a_sweep,
    scan_marks,
    scan_windows,
    shared_scanner,
)
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.pool import WorkPool
from tests.paths import ABNF_GRAMMARS, GBNF_GRAMMARS, GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES

NEEDS_VOCABULARY = frozenset({"think.gbnf"})
"""Token-terminal grammars cannot concretize without a tokenizer fixture."""

WORKERS = 8
"""Enough workers that the sweep really is windowed."""


def plans_of(compiled):
    """The certified plans for one artefact, in cascade order."""
    grammar = compiled.codegen_grammar
    return grammar, _safe_plans(
        _split_plans(grammar), compiled.split_analysis or compiled.grammar
    )


def both_selections(grammar, plans, text: str):
    """`(shared, alone)` cuts per plan — the two ways of reaching the rebase.

    ``alone`` is what each plan computed before the hoist: its own windows,
    rebased through its own scanner. ``shared`` is the one rebase every plan
    that reads a sweep now filters.
    """
    shared = shared_scanner(grammar, plans)
    with WorkPool(WORKERS) as pool:
        rebased = (
            shared.offsets(scan_windows(shared, text, WORKERS, pool), depth=0)
            if shared is not None
            else None
        )
        out = []
        for plan in plans:
            alone = plan.scanner.offsets(
                scan_windows(plan.scanner, text, WORKERS, pool), depth=0
            )
            seen = rebased if reads_a_sweep(plan) else None
            out.append(
                (
                    plan,
                    cut_offsets(plan, text, WORKERS, pool, seen),
                    cut_offsets(plan, text, WORKERS, pool, alone),
                    scan_marks(plan, text, WORKERS, pool, seen),
                    scan_marks(plan, text, WORKERS, pool, alone),
                )
            )
        return out


@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_plan_selects_the_same_cuts(bench) -> None:
    """Every certified plan of every bench grammar, on its own document."""
    text = bench.full or bench.corpus
    if len(text) < 2 * MIN_CHUNK:
        pytest.skip(f"{bench.name}: document below the split floor")
    grammar, plans = plans_of(bench.compiled)
    for plan, shared, alone, marks_shared, marks_alone in both_selections(
        grammar, plans, text
    ):
        assert marks_shared == marks_alone, (bench.name, plan.mark, "marks")
        assert shared == alone, (bench.name, plan.mark, "cuts")


@pytest.mark.parametrize(
    "name", [n for n in (*GBNF_GRAMMARS, *ABNF_GRAMMARS) if n not in NEEDS_VOCABULARY]
)
def test_every_ground_truth_plan_selects_the_same_cuts(name: str) -> None:
    """Both json formulations included — neither is privileged."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    text = '{"a": [1, 2, 3], "b": {"c": 1}}, ' * 400
    grammar, plans = plans_of(compiled)
    for plan, shared, alone, marks_shared, marks_alone in both_selections(
        grammar, plans, text
    ):
        assert marks_shared == marks_alone, (name, plan.mark, "marks")
        assert shared == alone, (name, plan.mark, "cuts")


def test_the_comparison_reaches_every_plan_kind() -> None:
    """The roster really supplies the kinds this claims to cover.

    Three shapes take different routes to their offsets — an envelope plan cuts
    on its own noise run, an opaque plan walks under its own region table, and
    everything else reads the shared sweep. A differential that only ever saw
    one of them would prove the hoist for one route.
    """
    kinds: set[str] = set()
    bearing = 0
    for bench in BENCHES:
        text = bench.full or bench.corpus
        if len(text) < 2 * MIN_CHUNK:
            continue
        _grammar, plans = plans_of(bench.compiled)
        for plan in plans:
            bearing += 1
            if plan.envelope is not None:
                kinds.add("envelope")
            elif plan.scanner.opaque:
                kinds.add("opaque")
            else:
                kinds.add("swept")
    assert bearing >= 4, f"only {bearing} certified plans across the roster"
    assert "swept" in kinds, f"no plan reads the shared sweep: {kinds}"
    assert len(kinds) >= 2, f"only one plan kind in the roster: {kinds}"


def test_a_grammar_with_several_sweeping_plans_shares_one_rebase() -> None:
    """The case the hoist exists for: more than one plan reading one sweep.

    With a single sweeping plan the shared rebase and the plan's own are the
    same computation done once either way, and the change would be invisible.
    """
    counts = []
    for bench in BENCHES:
        _grammar, plans = plans_of(bench.compiled)
        counts.append(sum(1 for plan in plans if reads_a_sweep(plan)))
    assert max(counts, default=0) >= 2, (
        f"no bench grammar certifies two sweeping plans: {counts}"
    )
