"""A sweep that cannot find anything is not dispatched.

`Scanner` keeps only those marks whose characters play no bracket role::

    self.separators = frozenset(m for m in derived.marks if not set(m) & paired)

So a grammar whose every mark character is also a bracket character is left
with an EMPTY separator set, and `rebase` reads `Window.marks` — such a scanner
can never report a mark, for any document, at any size. `scan_windows` used to
hand its windows to the pool regardless and sweep the whole document to learn
what the vocabulary already said before any text arrived.

The gate is exact rather than predictive: it fires only where the answer is
known empty in advance, so it cannot decide wrongly. What has to be defended is
therefore not its accuracy but its REACH — that it fires where it should, that
it is silent everywhere else, and that firing changes no answer.

Vacuity is the failure mode. A roster differential proves nothing if the gate
could never fire on the roster for the wrong reason, and a witness proves
nothing if it stopped being structurally empty. Both properties are asserted
rather than assumed.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.parsing.parallel.discovery.scan import Scanner, Window
from lexic.parsing.parallel.plan.cuts import rebase, scan_windows, shared_scanner
from lexic.parsing.parallel.planner import safe_plans, split_plans
from lexic.parsing.parallel.policy import MIN_CHUNK, MIN_SCAN
from lexic.parsing.parallel.pool import WorkPool
from tests.paths import GROUND_TRUTH
from tests.split_helpers import engages
from tools.benchmark.cases.grammars import BENCHES

EMPTY_SWEEP = 'root ::= grp+\ngrp ::= "(" word ")"\nword ::= [a-z]+\n'
"""A grammar whose only mark character is also its closing bracket.

Authored here because no bench grammar has the property — which is itself
`test_no_bench_grammar_sweeps_for_nothing`'s subject. Two other bracket-only
formulations were tried while writing this and get no shared scanner at all,
so they never sweep; this one does, which is what makes it the witness.
"""

WORKERS = (2, 4, 16)
"""Several counts, so no result rests on one window division."""


def empty_document(units: int) -> str:
    """An EMPTY_SWEEP document well above the chunk floor.

    Letters only: the unit's body is ``[a-z]+``, so a digit would make the
    document underivable and the parse would refuse it rather than answer.
    """
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    return "".join(
        "(" + alphabet[i % 26] * 4 + alphabet[(i // 26) % 26] + ")"
        for i in range(units)
    )


def sweeping_scanner(grammar):
    """The scanner the orchestrator would sweep this grammar with."""
    return shared_scanner(grammar, safe_plans(split_plans(grammar), grammar))


def witness():
    """The constructed grammar, compiled once per call site."""
    return compile_text(EMPTY_SWEEP, cache_key="empty-sweep-gate")


def witness_scanner() -> Scanner:
    """The witness's scanner, which every case here requires to exist.

    Separate from :func:`sweeping_scanner` because the roster cases must be
    able to see a ``None`` and say so, while these cannot proceed without one.
    """
    scanner = sweeping_scanner(witness().codegen_grammar)
    assert scanner is not None, "the witness must reach a sweep at all"
    return scanner


# ── the witness really is structurally empty ──────────────────────────────


def test_the_witness_sweeps_for_nothing() -> None:
    """The fixture holds the property every case below depends on.

    Without an empty separator set the gate cannot fire, and every assertion
    in this file would be checking the ungated path against itself.
    """
    scanner = witness_scanner()
    assert not scanner.opaque, "the witness must take the windowed path"
    assert not scanner.separators, "the witness stopped being structurally empty"
    assert scanner.openers and scanner.closers, (
        "the witness must still carry brackets — a scanner with nothing at all "
        "would be empty for a different reason than the one under test"
    )


def test_the_witness_sweep_really_returns_nothing() -> None:
    """Swept by hand, whole-document, the scanner finds no mark.

    The gate's licence is that the sweep is pointless. That is checked here
    against the real `Scanner.window`, not taken from the separator set.
    """
    scanner = witness_scanner()
    text = empty_document(4000)
    assert len(text) > 2 * MIN_SCAN, "the document must span several windows"
    assert scanner.window(text, 0, len(text)).marks == ()


# ── the gate fires, and changes no answer ─────────────────────────────────


@pytest.mark.parametrize("workers", WORKERS)
def test_an_empty_sweep_is_not_dispatched(workers: int) -> None:
    """One window comes back, and the pool is never asked for anything."""
    scanner = witness_scanner()
    text = empty_document(2000)
    handed: list[int] = []

    class Counting(WorkPool):
        """A pool that records every hand-out it is asked to make."""

        def map(self, work, items, beside=None):
            """Record the request, then behave exactly like the real pool."""
            handed.append(len(items))
            return super().map(work, items, beside)

    with Counting(workers) as pool:
        windows = scan_windows(scanner, text, workers, pool)
    assert windows == [Window(0, 0, 0, 0, ())]
    assert not handed, f"an empty sweep was dispatched anyway: {handed}"


@pytest.mark.parametrize("workers", WORKERS)
def test_the_gate_changes_no_offsets(workers: int) -> None:
    """The rebased offsets are what an honest full sweep would produce."""
    scanner = witness_scanner()
    text = empty_document(2000)
    with WorkPool(workers) as pool:
        gated = rebase(scanner, text, workers, pool)
    honest = scanner.offsets([scanner.window(text, 0, len(text))], depth=0)
    assert gated == honest == []


@pytest.mark.parametrize("workers", (1, 2, 4, 16))
def test_the_witness_still_parses_and_round_trips(workers: int) -> None:
    """The end the gate serves: same document, same text back."""
    compiled = witness()
    text = empty_document(2000)
    assert len(text) > 4 * MIN_CHUNK
    model = compiled.parse(text, cores=workers)
    assert model.to_text() == text
    assert model == compiled.parse(text, cores=1)


@pytest.mark.parametrize("workers", (4, 16))
def test_the_gate_declines_the_split_rather_than_raising(workers: int) -> None:
    """The single empty window costs nothing and never reaches an exception.

    The witness's only certified plan is exactly the empty-separator case, with
    no envelope and no region route to fall back on, so the split entry must
    decline outright — `engages` is what tells a decline from a model actually
    produced, which a round-trip alone cannot.
    """
    compiled = witness()
    text = empty_document(2000)
    assert not engages(compiled, text, cores=workers)


# ── the gate is silent on everything that can actually sweep ──────────────


def test_no_bench_grammar_sweeps_for_nothing() -> None:
    """The gate is inert on the roster, and the roster can still sweep.

    Both halves are the point. If no bench grammar reached a sweep, the
    inertness below would be vacuous; if one had an empty separator set, the
    gate would be changing a measured row.
    """
    reaching = {}
    for bench in BENCHES:
        scanner = sweeping_scanner(bench.compiled.codegen_grammar)
        if scanner is None or scanner.opaque:
            continue
        reaching[bench.name] = len(scanner.separators)
    assert len(reaching) >= 4, f"too few grammars reach a sweep: {reaching}"
    assert all(reaching.values()), f"a bench grammar sweeps for nothing: {reaching}"


@pytest.mark.parametrize("name", ("json.gbnf", "json.abnf"))
def test_a_ground_truth_json_grammar_is_untouched(name: str) -> None:
    """Both ground-truth formulations still answer as they did."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    scanner = sweeping_scanner(compiled.codegen_grammar)
    assert scanner is None or scanner.opaque or scanner.separators, (
        f"{name} now sweeps for nothing — the gate would change a real row"
    )
    document = (
        "{" + ", ".join(f'"k{i}": [1, 2, {{"b": "x, y"}}]' for i in range(200)) + "}"
    )
    assert len(document) > 2 * MIN_CHUNK
    assert compiled.parse(document, cores=4).to_text() == document


@pytest.mark.parametrize("workers", (2, 16))
@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_grammar_is_unchanged(bench, workers: int) -> None:
    """Every roster grammar parses to the same model it always did."""
    model = bench.compiled.parse(bench.full, cores=workers)
    assert model.to_text() == bench.full
    # Compared by dump: a left-nested model is as deep as its document, and
    # `==` recurses one C frame per level, so a long one raises RecursionError
    # on the COMPARISON while the parse and the model are both fine.
    assert model.dump() == bench.compiled.parse(bench.full, cores=1).dump()


# ── opacity decides before the empty-separator gate is ever asked ─────────


def opaque_separated_plan():
    """A real plan whose scanner is both OPAQUE and separator-bearing.

    `scan_windows` checks `scanner.opaque` first, so a scanner that hides
    marks inside a region must walk regardless of what its separator set
    holds — the empty-separator gate is a second, independent bound that
    never gets asked. Read off the real roster rather than hand-built, so the
    property under test is the grammar's own, not a fixture's.
    """
    for bench in BENCHES:
        grammar = bench.compiled.codegen_grammar
        for plan in safe_plans(split_plans(grammar), grammar):
            if plan.scanner.opaque and plan.scanner.separators:
                return bench, plan
    raise AssertionError("no bench grammar offers an opaque, separator-bearing plan")


@pytest.mark.parametrize("workers", WORKERS)
def test_an_opaque_scanner_with_separators_still_walks(workers: int) -> None:
    """Separators are not read at all once a scanner is opaque.

    The gate reads `separators` ONLY on the non-opaque path; an opaque
    scanner with a full separator set must still return the single walked
    window, never the arithmetic windows a non-empty set would otherwise earn.
    """
    bench, plan = opaque_separated_plan()
    scanner = plan.scanner
    document = bench.full
    with WorkPool(workers) as pool:
        windows = scan_windows(scanner, document, workers, pool)
    assert windows == [scanner.walk(document)]
