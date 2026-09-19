"""The plan loop's fallback, exercised: plan one declines, plan two wins.

`_split_plans` returns a TUPLE and the orchestrator iterates all of it — a plan
yielding no offsets is skipped and the next is tried. Nothing on the benchmark
roster reaches that: every grammar that tries a plan tries exactly one and it
wins, so the `+` that joins the certified family to the proposals, and the loop
that walks the result, have never had to cascade.

This is the witness. csv derives two plans in order — `row`, keyed on the
newline, then `field`, keyed on the comma — and a document that is ONE row of
many fields carries no newline at all. The first plan finds nothing to cut at,
the second cuts, and the model must still be the sequential one.

Nothing here is contrived: a single-row csv is an ordinary csv. The mechanism
was unexercised because every corpus document happens to have many rows.
"""

from __future__ import annotations

import pytest

from lexic.parsing.parallel import orchestrate
from lexic.parsing.parallel.orchestrate import _safe_plans, _split_plans
from tools.benchmark.cases.grammars import BENCHES

WORKERS = 4

ONE_ROW = ",".join(f"cell {n:04d}" for n in range(900))
"""One csv row of 900 fields — no newline, and past the per-worker floor."""


def csv_bench():
    """The roster's csv case."""
    return next(one for one in BENCHES if one.name == "csv")


def test_the_two_plans_are_ordered_row_then_field() -> None:
    """The premise: two survivors, and the one keyed on newlines is FIRST.

    If the order ever flips, the test below stops exercising the fallback and
    starts exercising the ordinary first-plan-wins path, silently.
    """
    grammar = csv_bench().compiled.codegen_grammar

    plans = _safe_plans(_split_plans(grammar), grammar)

    assert [one.owner for one in plans] == ["row", "field"]
    assert plans[0].mark == frozenset({"\n"})
    assert plans[1].mark == frozenset({","})


def test_the_first_plan_finds_nothing_and_the_second_produces() -> None:
    """The loop's own counters, on a document with no newline.

    Both halves are asserted, because either alone would pass for the wrong
    reason: that the first plan was CONSIDERED and yielded no offsets, and
    that the second was tried and PRODUCED the model.
    """
    # The loop's own decision points are private; instrumenting them IS the
    # test, and there is no public equivalent that reports which plan ran.
    # pylint: disable=protected-access
    bench = csv_bench()
    considered: list[tuple[str, int]] = []
    produced: list[str] = []
    fell_through: list[int] = []

    real_offsets = orchestrate.cut_offsets
    real_split = orchestrate._split_parse
    real_regions = orchestrate._split_regions

    def offsets(plan, text, cores, pool, seen):
        chosen = real_offsets(plan, text, cores, pool, seen)
        considered.append((plan.owner, len(chosen.offsets)))
        return chosen

    def split(parse, plan, ask, cuts, pool):
        model = real_split(parse, plan, ask, cuts, pool)
        if model is not None:
            produced.append(plan.owner)
        return model

    def regions(*args, **kwargs):
        fell_through.append(1)
        return real_regions(*args, **kwargs)

    orchestrate.cut_offsets = offsets
    orchestrate._split_parse = split
    orchestrate._split_regions = regions
    try:
        sequential = bench.compiled.parse(ONE_ROW, cores=1)
        split_model = bench.compiled.parse(ONE_ROW, cores=WORKERS)
    finally:
        orchestrate.cut_offsets = real_offsets
        orchestrate._split_parse = real_split
        orchestrate._split_regions = real_regions

    assert considered, "the loop never asked a plan for offsets"
    assert considered[0] == ("row", 0), f"plan one was not skipped: {considered}"
    assert ("field", 0) not in considered, "plan two found nothing to cut at"
    assert produced == ["field"], f"the second plan did not win: {produced}"
    assert not fell_through, "the loop fell through to the region routes"
    assert split_model.dump() == sequential.dump()
    assert split_model.to_text() == ONE_ROW


@pytest.mark.parametrize("cores", [2, 4, 8])
def test_the_fallback_answers_identically_at_every_width(cores: int) -> None:
    """A different width changes which cuts are proposed, not the value."""
    bench = csv_bench()

    sequential = bench.compiled.parse(ONE_ROW, cores=1)
    split_model = bench.compiled.parse(ONE_ROW, cores=cores)

    assert split_model.dump() == sequential.dump()
    assert split_model.to_text() == ONE_ROW
