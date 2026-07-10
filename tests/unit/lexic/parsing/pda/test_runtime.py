"""Tests for lexic.parsing.pda.runtime — the fused-runtime parity gate (Task 4).

:func:`~lexic.parsing.pda.runtime.parse_pda` builds a model directly during the
walk (fold fusion, no :class:`~lexic.parsing.earley.forest.ParseTree`). The
correctness bar is **user ruling 1**: ``semantic_dump()`` equality +
``to_text()`` round-trip against the engine's own
``fold.apply(parse_first(...))`` path — not raw ``model_dump()`` equality,
which may differ on ``semantic=False`` fields when the PDA's greedy loop
splits whitespace-like runs differently from the engine's.

Scoped to the four **island-free** ground-truth grammars (arithmetic.gbnf,
japanese.gbnf, list.gbnf, arithmetic.abnf — see the pinned island sets in
``test_analysis.py`` / ``test_clones.py``, all empty for these four): Task
4 leaves island references raising :exc:`~lexic.parsing.pda.runtime.PdaFail`
(Task 5's seam), so json/c/chess (island-bearing) are out of scope here. json
in particular already islands its ``ws`` rule (F1's soft-follower fix), so it
would report nothing but PdaFail on the runtime this task lands.

The one exception is a genuine sound residue, not a bug: a trailing loop whose
only overlap with its continuation is a *hard* follower (arithmetic's
``ws``-before-``"\\n"`` shape, pivot 4) stays predictive right up to a rare
input shape the PDA's stop-gate still refuses rather than risk a wrong model —
``PdaFail`` there is expected engine-fallback residue, not a mismatch.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import cast

import pytest

from lexic.base import GrammarModel
from lexic.codegen import build_codegen_grammar
from lexic.compile import (
    CompiledGrammar,
    canonical_grammar,
    compile_from_path,
    compile_text,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.grammars import GBNF_FLAVOUR, flavour_for_extension
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.clones import PdaTables, compile_pda
from lexic.parsing.pda.runtime import PdaFail, parse_pda
from tests.paths import GROUND_TRUTH

# ── fixtures ────────────────────────────────────────────────────────────

_ISLAND_FREE_STEMS: tuple[str, ...] = (
    "arithmetic.gbnf",
    "japanese.gbnf",
    "list.gbnf",
    "arithmetic.abnf",
)
_N_SEEDS = 50
_MAX_DEPTH = 4

# Mirrors tools/benchmark/pipeline_bench.py's arithmetic instance workload
# (same snippets, same ~4800-char target) — not imported (that module builds
# its own corpus for timing, not as an importable package) but pinned here as
# the same data so this test exercises the actual bench corpus shape.
_ARITHMETIC_BENCH_SNIPPETS: tuple[str, ...] = (
    "x=1\n",
    "y=z\n",
    "a+b=100\n",
    "foo=(bar)\n",
    "abc123-xyz=42\n",
)


def _arithmetic_bench_corpus(target_len: int = 4800) -> str:
    """The pinned arithmetic bench corpus, cycled to at least ``target_len`` chars."""
    pieces: list[str] = []
    size = 0
    n = 0
    while size < target_len:
        piece = _ARITHMETIC_BENCH_SNIPPETS[n % len(_ARITHMETIC_BENCH_SNIPPETS)]
        pieces.append(piece)
        size += len(piece)
        n += 1
    return "".join(pieces)


# ── helpers ───────────────────────────────────────────────────────────────


def _compiled_and_pda(path: Path) -> tuple[CompiledGrammar, PdaTables]:
    """Compile a ground-truth grammar both ways: the engine artifact + its PdaTables.

    Mirrors ``test_clones.py``'s ``_pda_for`` — the same inputs
    ``compile.py``'s (not-yet-landed) Task-6 wiring will use, built entirely
    through public seams: ``lifted`` from ``canonical_grammar`` +
    ``build_codegen_grammar`` + ``lift_optional_nullables``,
    ``instance_grammar``/``fold.config`` read off the already-compiled
    :class:`CompiledGrammar`.
    """
    flavour = flavour_for_extension(path)
    canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    compiled = compile_from_path(path)
    pda = compile_pda(lifted, compiled.instance_grammar, compiled.fold.config)
    return compiled, pda


def _specs(path: Path) -> dict:
    """The rule-name → IrRule view :func:`~lexic.generate.generate` walks."""
    flavour = flavour_for_extension(path)
    canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
    return {r.name: r for r in canonical.rules}


def _assert_parity(
    engine_model: GrammarModel, pda_model: GrammarModel, text: str
) -> None:
    """Assert ruling 1's semantic-parity contract, not raw ``model_dump()`` equality."""
    assert pda_model.semantic_dump() == engine_model.semantic_dump()
    assert pda_model.to_text() == text


# ── the parity gate (generated samples, per island-free grammar) ──────────


@pytest.mark.parametrize("stem", _ISLAND_FREE_STEMS)
def test_pda_engine_parity_on_generated_samples(stem: str) -> None:
    """PDA/engine parity across seeded generated samples of an island-free grammar.

    Skips generator-overshoot inputs the engine itself rejects. Tolerates the
    known arithmetic stop-set fallback residue (a small minority of samples,
    ruling 1's engine-fallback path — not a parity failure); any *other*
    grammar's :exc:`PdaFail` is a genuine, unexpected divergence and fails the
    test outright (these four are island-free — nothing should force a
    fallback).
    """
    path = GROUND_TRUTH / stem
    compiled, pda = _compiled_and_pda(path)
    specs = _specs(path)
    checked = fallbacks = 0
    for seed in range(_N_SEEDS):
        text = generate("root", specs, rng=random.Random(seed), max_depth=_MAX_DEPTH)
        if not text:
            continue  # a star/optional-rooted rule can roll an empty expansion
        try:
            engine_model = compiled.parse(text)
        except UnsupportedConstructError:
            continue  # generator overshoot the engine itself rejects
        try:
            pda_model = cast(GrammarModel, parse_pda(pda, text))
        except PdaFail:
            assert stem == "arithmetic.gbnf", (
                f"{stem}: unexpected PdaFail on {text!r} (island-free grammar)"
            )
            fallbacks += 1
            continue
        _assert_parity(engine_model, pda_model, text)
        checked += 1
    assert checked >= _N_SEEDS // 2, f"{stem}: too few samples actually checked"
    if stem == "arithmetic.gbnf":
        # Documented residue, not a regression trigger: a handful of the
        # trailing-ws-before-"\n" shapes fall back to the engine rather than
        # risk a wrong model (pivot 4 stop-set, F1's sound-islanding sibling).
        assert fallbacks <= _N_SEEDS // 4


# ── the pinned arithmetic bench corpus ─────────────────────────────────────


def test_pda_engine_parity_on_arithmetic_bench_corpus() -> None:
    """The pinned arithmetic bench corpus (pipeline_bench.py's instance workload).

    One whole-input parse; a PdaFail here means the corpus as a whole hit the
    documented stop-set residue shape (see the module docstring) — expected
    engine-fallback, asserted only as "did not raise anything unexpected"
    since the PDA either parses the *entire* corpus or defers all of it.
    """
    path = GROUND_TRUTH / "arithmetic.gbnf"
    compiled, pda = _compiled_and_pda(path)
    text = _arithmetic_bench_corpus()
    engine_model = compiled.parse(text)
    try:
        pda_model = cast(GrammarModel, parse_pda(pda, text))
    except PdaFail:
        return  # expected stop-set residue — the engine fallback covers it
    _assert_parity(engine_model, pda_model, text)


# ── the F1 semantic guard (Option B) ───────────────────────────────────────


def test_fail_island_raises_pdafail_regardless_of_fold():
    """A fail-island reference raises ``PdaFail`` even with a fold supplied.

    ``root ::= x "ab"?`` / ``x ::= [a-c]*`` — the same synthetic F1 shape
    ``test_clones.py`` compiles: ``x``'s stop-set escapes into the
    soft-only ``"ab"?`` follower, so ``x`` is flagged a *fail*-island
    (``IslandRef.fail``). Unlike an ordinary island, a fail-island reference
    raises before any sub-parse is attempted — supplying the engine's own
    fold (which would otherwise splice an island sub-model) makes no
    difference, proving the semantic F1 shape never silently produces the
    wrong model.
    """
    text = 'root ::= x "ab"?\nx ::= [a-c]*\n'
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    compiled = compile_text(text, flavour="gbnf")
    pda = compile_pda(lifted, normalize(lifted), compiled.fold.config)
    for inp in ("ab", "cab"):
        with pytest.raises(PdaFail):
            parse_pda(pda, inp, compiled.fold)
