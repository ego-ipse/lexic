"""Differential CI: PDA vs engine, across all 10 ground-truth grammars (Task 7).

Where :mod:`tests.unit.lexic.parsing.test_pda_kernel` scopes its parity gate to
the four **island-free** grammars, this module is the *wide* matrix: all 10
ground-truth grammars (islands included — c/chess/json/json_arr/json_ws all
carry at least one), each driven through both internal seams directly:

- **forced-PDA** — :func:`~lexic.parsing.pda_kernel.parse_pda` with the real
  fold supplied (so island references splice their Earley sub-parse);
- **forced-engine** — ``cg.fold.apply(parse_first(cg.instance_grammar, text,
  cg.tables))``, the same call :meth:`~lexic.compile.CompiledGrammar.parse`'s
  fallback branch makes.

The correctness bar is ruling 1 (semantic parity, not raw ``model_dump()``
equality — the PDA's greedy stop-set loop may split a ``semantic=False`` run
differently from the engine's ambiguity resolution): every sample where both
paths succeed asserts ``semantic_dump()`` equality plus a ``to_text()``
round-trip on *both* models. A forced-PDA ``PdaFail`` is a **fallback**, not a
failure — it is tallied, not asserted against (except that the engine path
alone must still round-trip). The raw ``model_dump()``-exact rate and the
fallback rate are *reported* (printed) per grammar, not gated — they feed the
effort's OUTCOME numbers, not a pass/fail bar.
"""

from __future__ import annotations

import random
from typing import cast

import pytest

from lexic.base import GrammarModel
from lexic.compile import (
    CompiledGrammar,
    canonical_grammar,
    compile_from_path,
    compile_text,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.grammars import flavour_for_extension
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.parsing import parse_first
from lexic.parsing.pda_kernel import PdaFail, parse_pda
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.test_pda_kernel import _arithmetic_bench_corpus

# ── fixtures ────────────────────────────────────────────────────────────

_ALL_STEMS: tuple[str, ...] = (
    "arithmetic.gbnf",
    "c.gbnf",
    "chess.gbnf",
    "japanese.gbnf",
    "json.gbnf",
    "json_arr.gbnf",
    "json_ws.gbnf",
    "list.gbnf",
    "arithmetic.abnf",
    "json.abnf",
)
_N_SEEDS = 40
_MAX_DEPTH = 4

# A couple of representative bench-shaped corpora. Arithmetic's is imported
# from test_pda_kernel.py (its own bench-corpus test already pins the same
# snippets/target length — reusing it, not re-pinning the literal, sidesteps
# the whole-tree pylint R0801 duplicate-code gate). json's mirrors
# tools/benchmark/pipeline_bench.py's ``_JSON_ITEMS``/``_json_corpus`` (same
# items, same target length) — pinned locally since nothing else in the test
# tree defines it yet; not imported from the benchmark module itself (the
# same "not a code donor for tests" precedent test_pda_kernel.py set).
_JSON_BENCH_ITEMS: tuple[str, ...] = (
    '{"name": "alpha", "id": 1, "ok": true}',
    '{"nested": {"a": [1, 2.5e3, -4], "b": null}}',
    '"quote \\" backslash \\\\ unicode \\u0041 tab \\t"',
    "-12.75e-2",
    '[true, false, null, 0, "s"]',
    '{"deep": [{"x": [[1], [2.0]]}], "y": false}',
)


def _json_bench_corpus(target_len: int = 4200) -> str:
    """One JSON document (single top-level array) of at least ``target_len`` chars."""
    items: list[str] = []
    total = 0
    i = 0
    while total < target_len:
        piece = _JSON_BENCH_ITEMS[i % len(_JSON_BENCH_ITEMS)]
        items.append(piece)
        total += len(piece) + 4
        i += 1
    return "[\n  " + ",\n  ".join(items) + "\n]\n"


_BENCH_CORPORA: dict[str, str] = {
    "arithmetic.gbnf": _arithmetic_bench_corpus(),
    "json.gbnf": _json_bench_corpus(),
}
"""Stem → its pinned bench-shaped corpus, for the two grammars whose bench
workloads are named in the plan's exit criterion (arithmetic) and whose
island density makes a long single-document differential worth pinning
(json)."""


class _Tally(dict):
    """A per-grammar sample tally — plain counters, printed, never asserted on."""

    def __init__(self) -> None:
        super().__init__(
            checked=0, pda_ok=0, fallback=0, engine_only=0, model_dump_exact=0
        )


_START_OVERRIDES: dict[str, str] = {
    # c's natural start ``root ::= (declaration)*`` is ``lo=0`` and rolls
    # empty 70% of the time (``generate``'s ``_pick_count``) — thin coverage
    # over 40 seeds. ``tests/property/conftest.py``'s ``c_statement_grammar``
    # fixture solves the identical problem the same way: drive generation
    # from "statement" instead (if/while/for/return/assignment/call/comments
    # — and c's own islands, e.g. ``relationoperator``/``statement-arm7``).
    "c.gbnf": "statement",
}


def _grammar_for(stem: str) -> tuple[CompiledGrammar, dict, str]:
    """Compile ``stem``, resolving its generation start rule.

    :returns: ``(compiled grammar, {rule_name: IrRule}, start rule name)`` —
        the start defaults to the grammar's own resolved start rule (so
        json/json.abnf generate from ``JSON-text``, not a hardcoded
        ``"root"``), overridden per :data:`_START_OVERRIDES` where the
        natural start gives thin coverage.
    """
    path = GROUND_TRUTH / stem
    override = _START_OVERRIDES.get(stem)
    if override is None:
        flavour = flavour_for_extension(path)
        canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
        specs = {r.name: r for r in canonical.rules}
        cg = compile_from_path(path)
        return cg, specs, str(canonical.start)
    text = path.read_text(encoding="utf-8") + f"\n# @start {override}\n"
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    specs = {r.name: r for r in canonical.rules}
    cg = compile_text(text, cache_key=f"pda-parity-{stem}-{override}-start")
    return cg, specs, override


def _forced_engine(cg: CompiledGrammar, text: str) -> GrammarModel:
    """Parse ``text`` via the forced-engine seam (bypassing the PDA entirely)."""
    tree = parse_first(cg.instance_grammar, text, cg.tables)
    return cast(GrammarModel, cg.fold.apply(tree))


def _check_one(cg: CompiledGrammar, text: str, tally: _Tally) -> None:
    """Run both seams on ``text``, tally the outcome, assert what parity demands.

    :raises UnsupportedConstructError: Propagated from the engine path on a
        generator-overshoot input the grammar itself rejects — the caller
        skips the sample rather than counting it.
    """
    engine_model = _forced_engine(cg, text)
    assert engine_model.to_text() == text
    if cg.pda is None:
        tally["checked"] += 1
        tally["engine_only"] += 1
        return
    try:
        pda_model = cast(GrammarModel, parse_pda(cg.pda, text, cg.fold))
    except PdaFail:
        tally["fallback"] += 1
        tally["checked"] += 1
        return
    tally["pda_ok"] += 1
    tally["checked"] += 1
    assert pda_model.semantic_dump() == engine_model.semantic_dump()
    assert pda_model.to_text() == text
    if pda_model.model_dump() == engine_model.model_dump():
        tally["model_dump_exact"] += 1


def _report(stem: str, cg: CompiledGrammar, tally: _Tally) -> None:
    """Print the per-grammar summary line (reported, not asserted)."""
    n = tally["checked"] or 1
    if cg.pda is None:
        print(
            f"{stem:16s} checked={tally['checked']:3d} ENGINE-ONLY (whole-grammar PDA opt-out)"
        )
        return
    islands = sorted(cg.pda.islands)
    exact = (
        f"{tally['model_dump_exact'] / tally['pda_ok']:5.1%}"
        if tally["pda_ok"]
        else "n/a"
    )
    print(
        f"{stem:16s} checked={tally['checked']:3d} "
        f"pda_ok={tally['pda_ok']:3d} "
        f"fallback_rate={tally['fallback'] / n:5.1%} "
        f"model_dump_exact_rate={exact} "
        f"islands({len(islands)})={islands}"
    )


# ── the wide matrix (seeded generated samples, all 10 grammars) ───────────


@pytest.mark.parametrize("stem", _ALL_STEMS)
def test_pda_engine_differential_on_generated_samples(stem: str) -> None:
    """Forced-PDA vs forced-engine parity across seeded samples of every grammar.

    Skips generator-overshoot inputs the engine itself rejects. A forced-PDA
    ``PdaFail`` is tallied as a fallback, not a failure. Every ground-truth
    grammar compiles a PDA under its own natural start rule — except c under
    the ``"statement"`` :data:`_START_OVERRIDES` start (an island itself, per
    ``test_analysis.py``'s pinned island set), which genuinely hits the
    whole-grammar opt-out (:attr:`~lexic.compile.CompiledGrammar.pda` is
    ``None``) — so this test also exercises that branch for real, not just
    defensively.
    """
    cg, specs, start = _grammar_for(stem)
    tally = _Tally()
    for seed in range(_N_SEEDS):
        text = generate(start, specs, rng=random.Random(seed), max_depth=_MAX_DEPTH)
        if not text:
            continue  # a star/optional-rooted rule can roll an empty expansion
        try:
            _check_one(cg, text, tally)
        except UnsupportedConstructError:
            continue  # generator overshoot the engine itself rejects
    assert tally["checked"] >= _N_SEEDS // 2, (
        f"{stem}: too few samples actually checked"
    )
    _report(stem, cg, tally)


# ── the pinned bench-shaped corpora (arithmetic, json) ─────────────────────


@pytest.mark.parametrize("stem", sorted(_BENCH_CORPORA))
def test_pda_engine_differential_on_bench_corpus(stem: str) -> None:
    """Forced-PDA vs forced-engine parity on one whole bench-shaped corpus.

    A ``PdaFail`` here means the corpus as a whole hit a fallback shape
    (arithmetic's documented trailing stop-set residue is the known one) —
    reported, not a failure; the forced-engine path must still round-trip.
    """
    path = GROUND_TRUTH / stem
    cg = compile_from_path(path)
    text = _BENCH_CORPORA[stem]
    tally = _Tally()
    _check_one(cg, text, tally)
    _report(f"{stem} (bench corpus)", cg, tally)
