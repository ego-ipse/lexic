"""One rebase per document answers what one rebase per plan answered.

`scan_marks` used to rebase the shared windows to absolute depth itself, once
for every plan a document asked. The orchestrator now does it once and hands
the offsets down. The claim that makes that legal is narrow and worth stating:
:meth:`~lexic.parsing.parallel.discovery.scan.Scanner.offsets` is a prefix sum
over the windows' own marks and deltas and reads nothing off the scanner, so
which plan asks cannot change what comes back.

A claim of that shape is proved by disagreement, not by inspection, so every
case here reads the same document THREE ways — the callee scanning for itself,
the shared offsets handed in, and a prefix sum restated by hand in this file —
and requires all three to agree. Two arms would let a mistake in the shared
form and a matching mistake in a restatement pass together; the third is
written out longhand here precisely so it cannot drift with either.

Vacuity is the failure mode this invites, in two ways. A grammar whose plans
all walk or cut on an envelope has no shared scanner at all, so comparing it
comes down to comparing the serial path with itself; and a document that yields
no mark at depth 0 makes every arm the empty list.
`test_the_roster_reaches_the_shared_rebase` and the non-empty assertions in
each case are what keep either from passing for nothing.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.parsing.parallel.discovery.scan import Window
from lexic.parsing.parallel.orchestrate import _safe_plans, _split_plans
from lexic.parsing.parallel.plan.cuts import (
    cut_offsets,
    reads_a_sweep,
    rebase,
    scan_marks,
    scan_windows,
    shared_scanner,
)
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.pool import WorkPool
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES

WORKERS = (2, 4, 16)
"""Three worker counts, so no result rests on one window division."""

JSON_GRAMMARS = ("json.gbnf", "json.abnf")
"""Both ground-truth json formulations. Both quote their strings, so both
carry an opaque interior and are REFUSED the shared sweep — which is the
property this file pins for them, rather than an equality it could not test."""


def hand_rebase(windows: list[Window]) -> list[int]:
    """The depth-0 prefix sum, restated longhand — the third arm.

    Deliberately not a call into `Scanner.offsets`: this is the computation the
    change moved, so a reading of it that shares no code with either arm is the
    only one that can catch both being wrong the same way.
    """
    found: list[int] = []
    running = 0
    for window in windows:
        for offset, relative, _segment in window.marks:
            if running + relative == 0:
                found.append(offset)
        running += window.delta
    return found


def sweeping_plans(grammar):
    """This grammar's certified plans, and the ones that read a sweep."""
    plans = _safe_plans(_split_plans(grammar), grammar)
    return plans, tuple(plan for plan in plans if reads_a_sweep(plan))


def three_arms(grammar, text: str, workers: int) -> tuple[int, int]:
    """Read every sweeping plan's marks three ways and require agreement.

    :returns: ``(plans compared, marks seen)`` — so a caller can refuse a case
        that compared nothing.
    """
    plans, sweepers = sweeping_plans(grammar)
    shared = shared_scanner(grammar, plans)
    if shared is None or not sweepers:
        return 0, 0
    seen = 0
    with WorkPool(workers) as pool:
        windows = scan_windows(shared, text, workers, pool)
        hoisted = rebase(shared, text, workers, pool)
        assert hoisted == hand_rebase(windows), (
            "the shared rebase and a longhand prefix sum disagree"
        )
        for plan in sweepers:
            scanned = scan_marks(plan, text, workers, pool)
            handed = scan_marks(plan, text, workers, pool, hoisted)
            longhand = scan_marks(plan, text, workers, pool, hand_rebase(windows))
            assert scanned == handed, f"{plan.mark}: the hoist changed the marks"
            assert scanned == longhand, f"{plan.mark}: longhand disagrees"
            seen += len(scanned)
    return len(sweepers), seen


# ── the roster, every bench grammar over its own document ─────────────────


@pytest.mark.parametrize("workers", WORKERS)
@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_grammar_rebases_identically(bench, workers: int) -> None:
    """Each bench grammar, its full document, three readings, three counts."""
    three_arms(bench.compiled.codegen_grammar, bench.full, workers)


@pytest.mark.parametrize("workers", WORKERS)
@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_grammar_cuts_identically(bench, workers: int) -> None:
    """The cuts chosen from the shared offsets are the cuts scanned for.

    `scan_marks` is the candidate set; `cut_offsets` is the choice made from
    it, and the two are separate passes. A hoist that preserved the candidates
    but shifted the choice would pass the test above and still split the
    document somewhere else.
    """
    grammar = bench.compiled.codegen_grammar
    plans, sweepers = sweeping_plans(grammar)
    shared = shared_scanner(grammar, plans)
    if shared is None or not sweepers:
        return
    with WorkPool(workers) as pool:
        hoisted = rebase(shared, bench.full, workers, pool)
        for plan in sweepers:
            assert cut_offsets(plan, bench.full, workers, pool) == cut_offsets(
                plan, bench.full, workers, pool, hoisted
            ), f"{plan.mark}: the hoist moved a cut"


def test_the_roster_reaches_the_shared_rebase() -> None:
    """The roster really exercises the hoist, by count rather than by name.

    Every equality above is vacuous on a grammar with no shared scanner, and
    most of the roster has none. If this stops holding, the file is comparing
    the serial path with itself and proves nothing.
    """
    reaching = {}
    for bench in BENCHES:
        plans, marks = three_arms(bench.compiled.codegen_grammar, bench.full, 4)
        if plans:
            reaching[bench.name] = (plans, marks)
    assert len(reaching) >= 4, f"only {sorted(reaching)} reach the shared rebase"
    assert sum(marks for _plans, marks in reaching.values()) >= 500, (
        f"too few marks compared for the equality to mean anything: {reaching}"
    )
    assert any(plans >= 2 for plans, _marks in reaching.values()), (
        "no grammar asks a second sweeping plan — the hoist is never exercised "
        f"on more than one rebase: {reaching}"
    )


# ── both json formulations: refused the sweep, and still answering ────────


@pytest.mark.parametrize("workers", (2, 8))
@pytest.mark.parametrize("name", JSON_GRAMMARS)
def test_a_quoted_json_grammar_takes_no_shared_rebase(name: str, workers: int) -> None:
    """Both ground-truth json grammars quote their strings, so neither reads a
    windowed sweep — and each still answers through the ordinary entry.

    Pinned rather than assumed: the refusal is asserted, so this case fails
    rather than passing vacuously if such a grammar ever becomes eligible.
    """
    grammar = compile_from_path(GROUND_TRUTH / name).codegen_grammar
    plans, sweepers = sweeping_plans(grammar)
    assert shared_scanner(grammar, plans) is None or not sweepers, (
        f"{name} now reads a shared sweep — this case no longer pins a refusal"
    )
    document = (
        "{" + ", ".join(f'"k{i}": [1, 2, {{"b": "x, y"}}]' for i in range(200)) + "}"
    )
    assert len(document) > 2 * MIN_CHUNK
    compiled = compile_from_path(GROUND_TRUTH / name)
    assert compiled.parse(document, cores=workers).to_text() == document


# ── the differential can fail ─────────────────────────────────────────────


SHIFTED = 'root ::= item+\nitem ::= "(" [a-z0-9]+ ")" ";"\n'
"""A grammar whose plan reads a sweep and whose document carries many marks —
so a perturbed rebase has something to be wrong about."""


def shifted_document(units: int) -> str:
    """A SHIFTED document long enough to clear the chunk floor."""
    return "".join(f"(unit{i});" for i in range(units))


def test_a_perturbed_rebase_is_caught() -> None:
    """Handing in offsets that are not the document's must NOT pass.

    Every case above compares `scan_marks` against `scan_marks`. If the
    supplied offsets were ignored — read off falsiness, say, or dropped — all
    of them would agree while the shared channel carried nothing. Dropping one
    offset must change the answer.
    """
    grammar = compile_text(SHIFTED, cache_key="shared-rebase-shifted").codegen_grammar
    text = shifted_document(900)
    assert len(text) > 2 * MIN_CHUNK
    plans, sweepers = sweeping_plans(grammar)
    shared = shared_scanner(grammar, plans)
    assert shared is not None and sweepers, "the fixture must read a shared sweep"

    with WorkPool(4) as pool:
        honest = rebase(shared, text, 4, pool)
        assert len(honest) > 2, "the fixture produced too few marks to perturb"
        for plan in sweepers:
            truthful = scan_marks(plan, text, 4, pool, honest)
            assert truthful, "the plan selected nothing — nothing was compared"
            # Drop an offset this plan SELECTS. The shared sweep reports every
            # mark of the grammar and each plan keeps its own, so removing the
            # first offset outright perturbs one the plan discards anyway and
            # the sabotage passes while proving nothing.
            dropped = [at for at in honest if at != truthful[0]]
            assert len(dropped) < len(honest)
            assert scan_marks(plan, text, 4, pool, dropped) != truthful


def test_an_empty_rebase_is_an_answer_not_an_absence() -> None:
    """A document with no mark at depth 0 must not trigger a rescan.

    The supplied offsets used to be windows, which are never empty; offsets
    are, and a form reading absence off falsiness would silently sweep the
    document again and return the marks the caller had just excluded.
    """
    grammar = compile_text(SHIFTED, cache_key="shared-rebase-shifted").codegen_grammar
    text = shifted_document(900)
    _plans, sweepers = sweeping_plans(grammar)
    with WorkPool(4) as pool:
        for plan in sweepers:
            assert scan_marks(plan, text, 4, pool, []) == []
            assert cut_offsets(plan, text, 4, pool, []).marks == []
