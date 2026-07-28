"""Tests for lexic.parsing.pda.runtime.runtime — the fused-runtime parity gate (Task 4).

:func:`~lexic.parsing.pda.runtime.reduce_runtime.pda_model` builds a model directly during the
walk (fold fusion, no :class:`~lexic.parsing.earley.kernel.forest.forest.ParseTree`). The
correctness bar is **user ruling 1**: ``semantic_dump()`` equality +
``to_text()`` round-trip against the engine's own
``fold.apply(parse_first(...))`` path — not raw ``dump()`` equality,
which may differ on ``semantic=False`` fields when the PDA's greedy loop
splits whitespace-like runs differently from the engine's.

Scoped to the four **island-free** ground-truth grammars (arithmetic.gbnf,
japanese.gbnf, list.gbnf, arithmetic.abnf — see the pinned island sets in
``test_analysis.py`` / ``test_clones.py``, all empty for these four): Task
4 leaves island references raising :exc:`~lexic.parsing.pda.runtime.runtime.PdaFail`
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
from typing import cast

import pytest

from lexic.compile import canonical_grammar, compile_from_path, compile_text
from lexic.compile.pipeline.passes import build_codegen_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.model import GrammarModel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_pda
from lexic.parsing.pda.compiler.specs import IslandRef
from lexic.parsing.pda.runtime import reduce_runtime as rrt
from lexic.parsing.pda.runtime.islands import IslandPolicy
from lexic.parsing.pda.runtime.reduce_runtime import pda_model, pda_reduce
from lexic.parsing.pda.runtime.runtime import PdaFail, PdaKernel
from tests.integration.pda_parity_helpers import (
    arithmetic_bench_corpus,
    deep_semantic,
    forced_engine,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import (
    assert_parity,
    compiled_and_pda,
    path_specs,
    reduce_pda,
    ref_reduce,
)

# ── fixtures ────────────────────────────────────────────────────────────

ISLAND_FREE_STEMS: tuple[str, ...] = (
    "arithmetic.gbnf",
    "japanese.gbnf",
    "list.gbnf",
    "arithmetic.abnf",
)
N_SEEDS = 50
MAX_DEPTH = 4


# ── the parity gate (generated samples, per island-free grammar) ──────────


@pytest.mark.parametrize("stem", ISLAND_FREE_STEMS)
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
    compiled, pda = compiled_and_pda(path)
    specs = path_specs(path)
    checked = fallbacks = 0
    for seed in range(N_SEEDS):
        text = generate("root", specs, rng=random.Random(seed), max_depth=MAX_DEPTH)
        if not text:
            continue  # a star/optional-rooted rule can roll an empty expansion
        try:
            engine_model = compiled.parse(text)
        except UnsupportedConstructError:
            continue  # generator overshoot the engine itself rejects
        try:
            built = pda_model(pda, text)
        except PdaFail:
            assert stem == "arithmetic.gbnf", (
                f"{stem}: unexpected PdaFail on {text!r} (island-free grammar)"
            )
            fallbacks += 1
            continue
        assert_parity(engine_model, built, text)
        checked += 1
    assert checked >= N_SEEDS // 2, f"{stem}: too few samples actually checked"
    if stem == "arithmetic.gbnf":
        # Documented residue, not a regression trigger: a handful of the
        # trailing-ws-before-"\n" shapes fall back to the engine rather than
        # risk a wrong model (pivot 4 stop-set, F1's sound-islanding sibling).
        assert fallbacks <= N_SEEDS // 4


# ── the pinned arithmetic bench corpus ─────────────────────────────────────


def test_pda_engine_parity_on_arithmetic_bench_corpus() -> None:
    """The pinned arithmetic bench corpus (pipeline_bench.py's instance workload).

    One whole-input parse; a PdaFail here means the corpus as a whole hit the
    documented stop-set residue shape (see the module docstring) — expected
    engine-fallback, asserted only as "did not raise anything unexpected"
    since the PDA either parses the *entire* corpus or defers all of it.
    """
    path = GROUND_TRUTH / "arithmetic.gbnf"
    compiled, pda = compiled_and_pda(path)
    text = arithmetic_bench_corpus()
    engine_model = compiled.parse(text)
    try:
        built = pda_model(pda, text)
    except PdaFail:
        return  # expected stop-set residue — the engine fallback covers it
    assert_parity(engine_model, built, text)


# ── per-parse interning (Task 5) ───────────────────────────────────────────


def _all_models(root: object) -> list[GrammarModel]:
    """Every :class:`GrammarModel` reachable from ``root``, self first (iterative)."""
    out: list[GrammarModel] = []
    stack: list[object] = [root]
    while stack:
        value = stack.pop()
        if isinstance(value, GrammarModel):
            out.append(value)
            stack.extend(getattr(value, name) for name in value._fields)
        elif isinstance(value, tuple):
            stack.extend(value)
    return out


_INTERN_CORPUS: dict[str, str] = {
    # repeated scalars (true/false/null/small ints) and repeated key strings
    "json.gbnf": '[true, true, false, true, 1, 1, 2, 2, "x", "x", null, null]',
    "chess.gbnf": "1. e4 e5\n2. e4 e5\n3. e4 e5\n4. e4 e5\n",
    "arithmetic.gbnf": "a=1\na=1\nb=2\nb=2\nc=3\nc=3\n",
}
"""Per-grammar inputs with many identical sub-structures — enough repetition
that interning provably collapses equal models to one instance."""


@pytest.mark.parametrize("stem", ["json.gbnf", "chess.gbnf", "arithmetic.gbnf"])
def test_interning_value_equality_parity(stem: str) -> None:
    """The interned PDA model equals the un-interned engine (``ModelFold``)
    reference for every instance case — value-equality parity under interning
    (Task 5's core gate; robust to islands, whose sub-models are spliced
    un-interned so equality — not identity — is the bar there)."""
    compiled = compile_from_path(GROUND_TRUTH / stem)
    text = _INTERN_CORPUS[stem]
    built = cast(GrammarModel, compiled.parse(text))
    engine_model = forced_engine(compiled, text)
    assert deep_semantic(built) == deep_semantic(engine_model)
    assert built.to_text() == text == engine_model.to_text()


def test_interning_shares_every_equal_submodel_island_free() -> None:
    """On an island-free grammar every build flows through the interning memo,
    so no two DISTINCT model instances are ``==`` — repeated sub-models collapse
    to one shared instance. (arithmetic.gbnf is island-free; the raw PDA run
    guarantees no engine-fallback bypass of the memo.)"""
    path = GROUND_TRUTH / "arithmetic.gbnf"
    compiled, pda = compiled_and_pda(path)
    text = _INTERN_CORPUS["arithmetic.gbnf"]
    built = pda_model(pda, text, compiled.fold)
    models = _all_models(built)
    by_value: dict[tuple[type, GrammarModel], int] = {}
    for model in models:
        first = by_value.setdefault((type(model), model), id(model))
        assert id(model) == first, (
            f"equal models not shared — {type(model).__name__} {model!r}"
        )
    assert len(by_value) < len(models), "corpus had no repeated sub-models to share"


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
            pda_model(pda, inp, compiled.fold)


# ── b1 reduce-path parity: _ReducePdaKernel vs earley_reduce ───────────────
#
# The grammar-text (reducer) twin of the parity gate above: self_grammar_pda's
# compiled reduce PDA parses grammar-text FRAGMENTS (GBNF source describing a
# one-rule grammar, e.g. 'root ::= "abc"') and must reduce byte-identically
# to the Earley reducer path (earley_reduce) — no ParseTree on the PDA side,
# just _ReducePdaKernel feeding cleaned children straight to the reduction
# bodies. Promoted verbatim from the throwaway
# zzz_current_work/260706-unified-parse-engine/gate_reduce.py three-gate
# harness (0 gate failures there).

REDUCE_GATE1_GBNF: tuple[str, ...] = (
    'root ::= "abc"',
    "root ::= [a-z]",
    'root ::= "a" | "b"',
    'root ::= "a"*',
    'root ::= "a" "b" "c"',
    'root ::= "a" ("b" | "c")+',
    "root ::= [0-9]+",
    'root ::= "x" [a-zA-Z_]*',
)
"""gate 1's positive-coverage floor: single-rule fragments the self-grammar
reduce PDA must handle end-to-end (no whole-input PdaFail, clone
completions > 0), each byte-equal to earley_reduce."""

REDUCE_GATE2_GBNF: tuple[str, ...] = (
    'root::="a"',
    'root  ::=  "a"   "b"',
    'root ::= "a"|"b"|"c"',
    "root ::=  [a-z]  [0-9]",
)
"""gate 2's capture-cleaning parity: varied whitespace noise around the same
shapes — the reduce PDA's cleaned children must reduce byte-identically to
the Earley path regardless of how the noise is laid out."""


@pytest.mark.parametrize("text", REDUCE_GATE1_GBNF)
def test_reduce_pda_gbnf_single_rule_fragment_is_end_to_end_and_byte_equal(
    text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gate 1: no PdaFail, at least one clone completion, byte-equal to earley_reduce."""
    completions = {"n": 0}
    kernel_cls = getattr(rrt, "_ReducePdaKernel")
    orig_complete = getattr(kernel_cls, "_complete")

    def _traced(self, frame):
        completions["n"] += 1
        orig_complete(self, frame)

    monkeypatch.setattr(kernel_cls, "_complete", _traced)
    pda = reduce_pda(GBNF_FLAVOUR)
    assert not isinstance(pda.start_key, IslandRef)
    got = pda_reduce(pda, text)
    assert completions["n"] > 0
    assert got == ref_reduce(GBNF_FLAVOUR, text)


@pytest.mark.parametrize("text", REDUCE_GATE2_GBNF)
def test_reduce_pda_gbnf_noise_variant_is_byte_equal_to_earley(text: str) -> None:
    """Gate 2: capture-cleaning parity across varied inter-token whitespace."""
    pda = reduce_pda(GBNF_FLAVOUR)
    assert not isinstance(pda.start_key, IslandRef)
    assert pda_reduce(pda, text) == ref_reduce(GBNF_FLAVOUR, text)


def test_reduce_pda_whole_ground_truth_corpus_matches_earley_where_recognised() -> None:
    """Gate 3: over every ground-truth grammar file (fed as grammar TEXT, both
    flavours), wherever the self-grammar reduce PDA recognises a whole file
    end-to-end it is byte-equal to earley_reduce — asserted; how OFTEN it
    recognises a whole file is counted, not asserted (per the harness this is
    promoted from: today every ground-truth file, being multi-rule, whole-input
    falls back to Earley — 0 recognised, 0 mismatched, out of 8 GBNF + 2 ABNF
    files — matching gate_reduce.py's own gate-3 output; the gate that matters
    here is the absence of a silent MISMATCH). Both flavours now compile a real
    reduce PDA (the ``rulelist`` boundary-shift left-factor removed ABNF's start
    island).
    """
    for flavour in (GBNF_FLAVOUR, ABNF_FLAVOUR):
        pda = reduce_pda(flavour)
        corpus = sorted(GROUND_TRUTH.glob(f"*{flavour.extensions[0]}"))
        assert corpus
        assert not isinstance(pda.start_key, IslandRef)
        recognised = mismatched = 0
        for path in corpus:
            text = path.read_text(encoding="utf-8")
            try:
                got = pda_reduce(pda, text)
            except PdaFail:
                continue
            if got == ref_reduce(flavour, text):
                recognised += 1
            else:
                mismatched += 1
        assert mismatched == 0


# ── one vocabulary for one concern ─────────────────────────────────────


def test_kernel_and_islands_share_one_policy_record():
    """The kernel holds the SAME record it hands an island, not a twin of it.

    `fold` and the resolver were carried by two records that ordered their
    fields differently — the kernel's and the island's — and the only thing
    keeping the hand-off correct was that one call site spelled the swap
    right. One record cannot be handed over wrong.
    """
    compiled, pda = compiled_and_pda(GROUND_TRUTH / "json.gbnf")

    def take_first(first, _other):
        return first

    kern = PdaKernel(pda, "{}", compiled.fold, resolve=take_first)
    assert isinstance(kern.policy, IslandPolicy)
    assert kern.policy.fold is compiled.fold
    assert kern.policy.resolve is take_first
    assert kern.policy.delegates is None  # filled per island, at the reference
