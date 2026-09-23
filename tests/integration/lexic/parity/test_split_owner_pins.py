"""What the planner CHOOSES today, pinned before the owner selection changes.

The terminated route carries nine of the roster's splitting rows, so widening
it to descend past the start rule is a change under everything that works. This
suite is what stands between that descent and a silent regression: it records
the route each row takes, the owner and mark the planner derives, and whether
the row splits at all — and every one of those must survive the change.

**What it deliberately does NOT pin: cut counts.** Measured five times per row,
the pieces a parse actually makes vary with thread timing — `vyx` gives 3 or 4
at four workers, `dense-earley` 3 or 4 at sixteen. A pinned count would fail on
a slow machine for reasons that have nothing to do with the planner, and a
range wide enough to be safe would be too wide to catch anything. What is
pinned instead is the fact of splitting, which is stable, and the model, which
is the property that actually matters.

**Four rows split with no owner to pin.** `json`, `nested`, `vyx` and
`island-earley` reach `_split_regions` — the region SOURCES, which divide
without a `SplitPlan` at all — so their pin here is behavioural only. That is a
fact about the parallel layer having two split paths, not a gap in this suite;
each source pins its own plan by name in its own file.
"""

from __future__ import annotations

import pytest

from lexic.parsing.parallel import orchestrate, replicas
from lexic.parsing.parallel.planner import split_plan
from lexic.parsing.parallel.stitch import interior, tasks
from tools.benchmark.cases.grammars import BENCHES

# row -> (owner, mark) the planner derives today; None where it derives no plan
OWNERS: dict[str, tuple[str, str] | None] = {
    "arithmetic": ("term", "+"),
    "csv": ("row", "\n"),
    "json": None,
    "gbnf-meta": ("rule", "\t"),
    "abnf-meta": ("rule", "\n"),
    "vyx": None,
    "markdown": ("block", "\n"),
    "nested": None,
    "lexruns": ("entry", "\n"),
    "backtrack": ("stmt", "\n"),
    "mixedends": ("record", "\n"),
    "announced": ("section", "\n"),
    "split-nullable": ("para", "\n"),
    "wrapped-unit": None,
    "dense-earley": ("line", "\n"),
    # island-earley derives no SplitPlan and splits anyway, through the folded
    # SOURCE — the fourth row to do so, beside json, nested and vyx. Its owner
    # and mark are pinned by name where that source's plan lives, in
    # `test_folded_spine_split`; here it is `None` because that is what the
    # PLANNER derives, which is what this table is about.
    "island-earley": None,
    # The three engine-reach rows derive no plan and no folded source either.
    # Their reason is now distinct from island-earley's and worth naming: the
    # fold TAKES each of them, but the recursive arm's remainder is a bare
    # literal (`A ::= A "a" | "a"`), so there is no separator RULE — nothing to
    # spell a mark, and nothing to re-parse a removed one under.
    "start-fallback": None,
    "interior-exact": None,
    "interior-climb": None,
}

# row -> whether a parse at four workers divides the document at all
SPLITS: dict[str, bool] = {
    "arithmetic": True,
    "csv": True,
    "json": True,
    "gbnf-meta": True,
    "abnf-meta": True,
    "vyx": True,
    "markdown": True,
    "nested": True,
    "lexruns": True,
    "backtrack": True,
    "mixedends": True,
    "announced": True,
    "dense-earley": True,
    # split-nullable and wrapped-unit both divide: each reaches a terminated
    # interior. wrapped-unit's sits one rule deeper than the old two-slot
    # route could express — the route is a PATH now, one step per descent, so
    # depth is no longer a bound.
    "split-nullable": True,
    "wrapped-unit": True,
    # island-earley divides through the folded SOURCE. It has no repetition
    # the grammar STATES — which is why no route shape ever reached it — but
    # the predictive path folds `expr ::= expr addop term | term` into
    # `term (addop term)*`, and the source reads that shape analysis to find
    # the spine. The separator is ` + ` / ` - `, owned by `term`.
    "island-earley": True,
    # These three never divide, and their reason is NOT island-earley's. The
    # fold takes each of them too, but `A ::= A "a" | "a"` has no separator
    # rule between its terms, so the source declines before any boundary proof
    # is asked — measured at four workers on the full sample: zero
    # piece-parses, not one.
    "start-fallback": False,
    "interior-exact": False,
    "interior-climb": False,
}

_SITES = (orchestrate, interior, tasks, replicas)
ROWS = tuple(bench.name for bench in BENCHES)


def bench_named(name: str):
    """The roster entry for ``name``."""
    return next(one for one in BENCHES if one.name == name)


def pieces(bench, text: str, cores: int, patch: pytest.MonkeyPatch) -> int:
    """How many piece-parses a run makes — counted at EVERY import site.

    `worker_parse` is imported by name into four modules, so patching the
    defining module alone counts none of the region route's pieces and reads a
    splitting row as sequential. That is a measurement bug this helper exists
    to not have.
    """
    seen = [0]
    real = replicas.worker_parse

    def spy(*args, **kwargs):
        """Count one piece, then parse it."""
        seen[0] += 1
        return real(*args, **kwargs)

    for site in _SITES:
        if hasattr(site, "worker_parse"):
            patch.setattr(site, "worker_parse", spy)
    bench.compiled.parse(text, cores=cores)
    return seen[0]


@pytest.mark.parametrize("name", ROWS)
def test_the_planner_derives_the_owner_it_derives_today(name: str) -> None:
    """The owner and mark are a pure function of the grammar — pin both.

    A descent that changed which rule owns the cut on a row that already works
    would reroute a working split through an untested path, and the model would
    be the only thing left to catch it.
    """
    plan = split_plan(bench_named(name).compiled.codegen_grammar)
    expected = OWNERS[name]

    if expected is None:
        assert plan is None, f"{name} gained a plan it did not have"
        return
    assert plan is not None, f"{name} lost its plan"
    assert plan.owner == expected[0]
    assert expected[1] in plan.mark


@pytest.mark.parametrize("name", ROWS)
def test_a_row_that_divides_today_still_divides(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Splitting is pinned as a FACT, not as a count.

    The count moves with thread timing; whether the document was divided at all
    does not. For the three rows the descent is for, this pins today's answer so
    the change that flips them is visible as a change.
    """
    bench = bench_named(name)
    bench.compiled.parse(bench.full, cores=1)  # warm

    divided = pieces(bench, bench.full, 4, monkeypatch) > 1

    assert divided is SPLITS[name], f"{name}: splits={divided}, pinned {SPLITS[name]}"


@pytest.mark.parametrize("name", ROWS)
@pytest.mark.parametrize("cores", [2, 4, 16])
def test_the_divided_model_is_the_sequential_model(name: str, cores: int) -> None:
    """The property the whole parallel layer exists to preserve.

    Compared against the model THIS tree produces at one worker — not a
    re-derived baseline. A split that changed the parse's meaning and a split
    that reassembled it wrongly are the same failure here, which is correct:
    both are a document that means something else after being divided.
    """
    bench = bench_named(name)

    once = bench.compiled.parse(bench.full, cores=1)
    many = bench.compiled.parse(bench.full, cores=cores)

    assert many.dump() == once.dump()
    assert many.to_text() == once.to_text() == bench.full
