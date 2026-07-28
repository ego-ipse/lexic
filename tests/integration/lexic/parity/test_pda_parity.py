"""Differential CI: PDA vs engine, across all 10 ground-truth grammars (Task 7).

Where :mod:`tests.unit.lexic.parsing.pda.test_runtime` scopes its parity gate to
the four **island-free** grammars, this module is the *wide* matrix: all 10
ground-truth grammars (islands included — c/chess/json/json_arr/json_ws all
carry at least one), each driven through both internal seams directly:

- **forced-PDA** — :func:`~lexic.parsing.pda.runtime.reduce_runtime.pda_model` with the real
  fold supplied (so island references splice their Earley sub-parse);
- **forced-engine** — ``cg.fold.apply(parse_first(prod(cg).instance_grammar, text,
  prod(cg).tables))``, the same call :meth:`~lexic.compile.CompiledGrammar.parse`'s
  fallback branch makes.

The correctness bar is ruling 1 (semantic parity, not raw ``dump()``
equality — the PDA's greedy stop-set loop may split a ``semantic=False`` run
differently from the engine's ambiguity resolution): every sample where both
paths succeed asserts deep semantic equality (:func:`deep_semantic` —
``semantic=False`` binds dropped at every level) plus a ``to_text()``
round-trip on *both* models. A forced-PDA ``PdaFail`` is a **fallback**, not a
failure — it is tallied, not asserted against (except that the engine path
alone must still round-trip). The raw ``dump()``-exact rate and the
fallback rate are *reported* (printed) per grammar, not gated — they feed the
effort's OUTCOME numbers, not a pass/fail bar.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.parsing.pda.compiler.clones import KTupleGate, PeekGate
from lexic.parsing.pda.compiler.flatten import all_clones
from lexic.parsing.pda.compiler.specs import IslandRef
from lexic.parsing.pda.runtime.reduce_runtime import pda_model
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import earley_model
from tests.integration.lexic.parity.pda_parity_helpers import (
    check_one,
    deep_semantic,
    forced_engine,
    grammar_for,
    json_bench_corpus,
    report,
)
from tests.paths import ABNF_GRAMMARS, GBNF_GRAMMARS, GROUND_TRUTH
from tests.unit.lexic.parsing.parsing_helpers import prod
from tests.unit.lexic.parsing.pda.runtime.test_runtime import arithmetic_bench_corpus

# ── fixtures ────────────────────────────────────────────────────────────

# The wide matrix: every GBNF ground-truth grammar bar vyx (whose non-default
# @start corpus is exercised elsewhere) and think (a token grammar — generating
# samples needs a tokenizer to spell token atoms, out of this text-only matrix's
# scope) plus both ABNF grammars.
_SKIP_STEMS = frozenset({"vyx.gbnf", "think.gbnf"})
ALL_STEMS: tuple[str, ...] = (
    *(g for g in GBNF_GRAMMARS if g not in _SKIP_STEMS),
    *ABNF_GRAMMARS,
)
N_SEEDS = 40
MAX_DEPTH = 4

# A couple of representative bench-shaped corpora. Arithmetic's is imported
# from test_runtime.py (its own bench-corpus test already pins the same
# snippets/target length — reusing it, not re-pinning the literal, sidesteps
# the whole-tree pylint R0801 duplicate-code gate).
BENCH_CORPORA: dict[str, str] = {
    "arithmetic.gbnf": arithmetic_bench_corpus(),
    "json.gbnf": json_bench_corpus(),
}
"""Stem → its pinned bench-shaped corpus, for the two grammars whose bench
workloads are named in the plan's exit criterion (arithmetic) and whose
island density makes a long single-document differential worth pinning
(json)."""


class Tally(dict):
    """A per-grammar sample tally — plain counters, printed, never asserted on."""

    def __init__(self) -> None:
        super().__init__(checked=0, pda_ok=0, fallback=0, engine_only=0, dump_exact=0)


# ── the wide matrix (seeded generated samples, all 10 grammars) ───────────


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_pda_engine_differential_on_generated_samples(stem: str) -> None:
    """Forced-PDA vs forced-engine parity across seeded samples of every grammar.

    NOT a duplicate of the raw-equality test below, and the division matters.
    This is the BROAD differential: it tallies fallbacks, round-trips BOTH
    models, and exercises the whole-grammar opt-out branch for real (c's
    override start). It compares at the SEMANTIC bar, which is weaker, and that
    is deliberate — it is checking that the two paths behave alike across every
    grammar and every escape, not that they build byte-identical models.

    `test_both_engines_build_the_same_model_not_just_the_same_meaning` owns the
    equality invariant, at the raw bar, on the grammars that hold it. Two tests,
    two jobs; neither subsumes the other.

    Skips generator-overshoot inputs the engine itself rejects. A forced-PDA
    ``PdaFail`` is tallied as a fallback, not a failure. Every ground-truth
    grammar compiles a PDA under its own natural start rule — except c under
    the ``"statement"`` :data:`_START_OVERRIDES` start (an island itself, per
    ``test_analysis.py``'s pinned island set), which genuinely hits the
    whole-grammar opt-out (:attr:`~lexic.compile.CompiledGrammar.pda` is
    ``None``) — so this test also exercises that branch for real, not just
    defensively.
    """
    cg, specs, start = grammar_for(stem)
    tally = Tally()
    for seed in range(N_SEEDS):
        text = generate(start, specs, rng=random.Random(seed), max_depth=MAX_DEPTH)
        if not text:
            continue  # a star/optional-rooted rule can roll an empty expansion
        try:
            check_one(cg, text, tally)
        except UnsupportedConstructError:
            continue  # generator overshoot the engine itself rejects
    assert tally["checked"] >= N_SEEDS // 2, f"{stem}: too few samples actually checked"
    report(stem, cg, tally)


# ── the pinned bench-shaped corpora (arithmetic, json) ─────────────────────


@pytest.mark.parametrize("stem", sorted(BENCH_CORPORA))
def test_pda_engine_differential_on_bench_corpus(stem: str) -> None:
    """Forced-PDA vs forced-engine parity on one whole bench-shaped corpus.

    A ``PdaFail`` here means the corpus as a whole hit a fallback shape
    (arithmetic's documented trailing stop-set residue is the known one) —
    reported, not a failure; the forced-engine path must still round-trip.
    """
    path = GROUND_TRUTH / stem
    cg = compile_from_path(path)
    text = BENCH_CORPORA[stem]
    tally = Tally()
    check_one(cg, text, tally)
    report(f"{stem} (bench corpus)", cg, tally)


# ── P2 k-window demotion — the anti-trap gates (Task 6.3 part c) ──────────
#
# Island-move + byte-parity alone are insufficient here: a demoted decision
# compiled with an empty/wrong gate would mis-parse → PdaFail → engine
# fallback, so both gates would PASS while the PDA is unsound AND slower
# (task63fix finding F2). These tests therefore drive the demoted decisions
# through ``pda_model`` directly — a ``PdaFail`` IS a failure, no fallback
# masks a wrong gate — and pin the gates' structural presence.

CHESS_ADVERSARIAL: tuple[str, ...] = (
    "1. e4 e5\n2. Nf3 Nf6\n",  # plain nonpawn — the take/skip skip side
    "1. Nbd2 Ngf6\n2. N1d2 Qh4+\n",  # file + rank disambiguation (take side, k=3)
    "1. Nxe4 Nfxe4\n2. exd5 O-O\n",  # captures with and without disambiguation
    "1. e8=Q Kxe8\n2. Nb1xd2 Rfe8+\n",  # promotion; full file+rank+capture form
    "1. e4 e5\n2. Nf3 Nc6\n3. Bb5 a6\n",  # multi-line loop continuation
)


def test_p2_chess_parses_pure_pda_with_zero_fallback() -> None:
    """Chess is island-free post-P2 (``nonpawn`` demoted at k=3) and every
    adversarial disambiguation input parses on the pure PDA — an empty or
    wrong loop gate would raise ``PdaFail`` right here. The structural pin
    reads the spec table (the compiler intermediate; ``all_clones`` cannot
    walk past dispatch/ref targets from the start shell)."""
    cg = compile_from_path(GROUND_TRUTH / "chess.gbnf")
    assert not isinstance(prod(cg).pda.start_key, IslandRef)
    assert sorted(prod(cg).pda.islands) == []
    nonpawn = [
        spec for key, spec in prod(cg).pda.clones.items() if key.name == "nonpawn"
    ]
    assert nonpawn, "nonpawn must be cloned now (demoted, not islanded)"
    assert any(
        isinstance(item.gate, KTupleGate)
        for spec in nonpawn
        for arm in spec.arms
        for item in arm.specs
    ), "the demoted nonpawn loop must carry a k-window gate"
    for text in CHESS_ADVERSARIAL:
        built = pda_model(prod(cg).pda, text, cg.fold)
        engine_model = forced_engine(cg, text)
        assert deep_semantic(built) == deep_semantic(engine_model)
        assert built.to_text() == text


def test_p2_lo_gt_k_arm_gate_is_eof_exact_end_to_end() -> None:
    """The ``lo > k`` → k=3 digit-vs-EOF arm separation (the re-bless hard
    constraint) exercised through the real compiled runtime: selecting
    ``"12"`` requires the EOF-carrying window position to match exactly at
    end-of-input, never a generic character."""
    cg = compile_text(
        'root ::= [0-9]{4,} "x" | "12"\n', flavour="gbnf", cache_key="p2-lo-gt-k-eof"
    )
    assert not isinstance(prod(cg).pda.start_key, IslandRef)
    assert not prod(cg).pda.islands
    clones = all_clones([prod(cg).pda.program.start])
    assert any(clone.kwin_selectors is not None for clone in clones), (
        "the demoted alternation must select by k-window"
    )
    assert pda_model(prod(cg).pda, "12", cg.fold).to_text() == "12"
    for text in ("1234x", "1234567x"):
        assert pda_model(prod(cg).pda, text, cg.fold).to_text() == text
    with pytest.raises(PdaFail):
        pda_model(
            prod(cg).pda, "123x", cg.fold
        )  # 3 digits < lo=4 — in no arm's language


# ── P3 noise-skip peek — the anti-trap gates (Task 6.4) ────────────────────

JSON_ADVERSARIAL: tuple[str, ...] = (
    # THE regression sample: the stored peek gate must be honored in every
    # clone — a clone whose HARD tail doesn't overlap the loop FIRST would
    # otherwise compile a whitespace-admitting stop-set that eats the " ]"
    # noise run (caught live during Task 6.4; pinned forever).
    '{ "x" : [ 1 , 2 ,\t3 ] ,\n "y" : { } }',
    '{"a": [1, 2.5e-3, "s", true, null], "b": {"c": false}}',
    "  [ 1 ]  ",
    "[ ]",
    '{ "a" : [ ] , "b" : { "c" : [ 1 , [ 2 ] ] } }',
    "[ 1\t,\n 2 ,  3 ]",
)


def test_p3_json_parses_pure_pda_with_zero_fallback() -> None:
    """json is island-free post-P3 (``value``/``*-item2`` peek-demoted on top
    of P6's ``ws``) and whitespace-heavy adversarial inputs parse on the pure
    PDA — driven through ``pda_model`` directly, so a wrong peek gate fails
    here rather than hiding behind the engine fallback."""
    cg = compile_from_path(GROUND_TRUTH / "json.gbnf")
    assert not isinstance(prod(cg).pda.start_key, IslandRef)
    assert sorted(prod(cg).pda.islands) == []
    value_clones = [s for key, s in prod(cg).pda.clones.items() if key.name == "value"]
    assert value_clones
    assert all(arm.peek is not None for spec in value_clones for arm in spec.arms), (
        "value must select by post-noise peek"
    )
    item2 = [s for key, s in prod(cg).pda.clones.items() if key.name == "array-item2"]
    assert item2
    assert any(
        isinstance(item.gate, PeekGate)
        for spec in item2
        for arm in spec.arms
        for item in arm.specs
    ), "the array-item loop must carry a peek gate"
    for text in JSON_ADVERSARIAL:
        built = pda_model(prod(cg).pda, text, cg.fold)
        engine_model = forced_engine(cg, text)
        assert deep_semantic(built) == deep_semantic(engine_model)
        assert built.to_text() == text


# Every corpus grammar the two engines agree on at RAW equality. `vyx.gbnf` is
# the one exclusion and it is a KNOWN DEFECT, not a licence: its residual is the
# ARM class — one span through two different productions that mean different
# things — where a length preference has no standing. Adding it here is the
# fails-before test for that fix.
RAW_PARITY_STEMS: tuple[str, ...] = tuple(
    stem for stem in ALL_STEMS if stem not in {"vyx.gbnf"}
)
"""Only `vyx.gbnf` is out, and it is a named defect rather than a licence."""

RAW_PARITY_STARTS: dict[str, str] = {
    # c needs a start chosen for THIS bar. `START_OVERRIDES` drives the wide
    # differential from `statement`, which is right there — it reaches c's own
    # islands (`relationoperator`, `statement-arm7`) and so exercises the
    # fallback that test owns. But the PDA escapes on 200 of 200 inputs from
    # `statement`, every sample skipped, so the raw bar compared NOTHING and its
    # own guard fired.
    #
    # `declaration` is `root ::= (declaration)*`'s own body, so it is the
    # language c actually describes rather than a leaf picked to be easy, and it
    # is non-empty on every seed and predictive on every seed (measured: 40/40
    # parsed by the PDA, 0 escapes, 0 empty). The two tests need different
    # starts because they exercise different paths; that is not a bar change.
    "c.gbnf": "declaration",
}
"""Generation starts for the RAW bar, where the wide matrix's start would skip
every sample. Chosen to stay on the predictive path — never to weaken the
comparison."""


@pytest.mark.parametrize("stem", RAW_PARITY_STEMS)
def test_both_engines_build_the_same_model_not_just_the_same_meaning(
    stem: str,
) -> None:
    """Raw model equality, not `deep_semantic` — the engines must agree.

    Ruling 1 set the bar at semantic parity because "the PDA's greedy stop-set
    loop may split a `semantic=False` run differently from the engine's
    ambiguity resolution". That licence made 47 of 200 json inputs invisible:
    the same characters landing in different `Ws` fields. Under the ruling that
    the engines are REQUIRED to agree, the split has one defined answer and
    both paths must produce it — `deep_semantic` would pass either way, so it
    cannot be the test for this.

    This test owns the EQUALITY invariant and nothing else — the broad
    differential above owns fallback behaviour, round-trip and the opt-out
    branch, at the weaker semantic bar. Neither subsumes the other.

    Ruled 2026-07-28: the bar is RAW model equality, not `deep_semantic`. A
    grammar declaring a rule `@non-semantic` does not remove it from the model —
    it is preserved as fields, because round-trip needs the characters stored —
    so a consumer reading those fields CAN see a difference the semantic bar
    calls invisible.

    Every corpus grammar but one holds at this bar; `vyx.gbnf` is excluded and
    named in `RAW_PARITY_STEMS` as a known defect, not a licence. `c.gbnf`
    needs its own generation start (`RAW_PARITY_STARTS`) to reach the
    predictive path at all — the wide matrix's start escapes to islands on
    every sample, which compared nothing.
    """
    cg, rules, start = grammar_for(stem, RAW_PARITY_STARTS.get(stem))
    product = prod(cg)
    differed: list[str] = []
    checked = 0
    for seed in range(200):
        text = generate(start, rules, rng=random.Random(seed), max_depth=12)
        if not text:
            continue
        try:
            want = forced_engine(cg, text)
            got = pda_model(product.pda, text, cg.fold)
        except PdaFail, UnsupportedConstructError:
            continue
        checked += 1
        if repr(got) != repr(want):
            differed.append(f"seed={seed} text={text!r}")
    assert checked, f"{stem}: nothing compared — the test proves nothing"
    assert not differed, (
        f"{stem}: {len(differed)} of {checked} inputs build different models; "
        f"first: {differed[0]}"
    )


# ── an arm choice is refused, not silently picked ────────────────────────

_ARM_AMBIGUOUS = """root ::= line
line ::= plain | forced
plain ::= [a-z#]+
forced ::= "#" [a-z]*
"""
"""One span, two DIFFERENT productions. `#ab` is `plain` whole, or `forced` as
`#` then `ab` — an arm choice, which is exactly what vyx's `inline-content`
does and what a split is not."""


def test_the_pda_refuses_an_arm_choice_rather_than_answering_it() -> None:
    """The island gate must run even when the fast path built a tree.

    `island_parse` used to treat `FastTree` succeeding as proof of unambiguity.
    It is not: measured, `FastTree.build` returns a tree for a completion whose
    arms mean different things, so the gate never ran and the PDA answered
    `Forced('#ab')` for an input it had itself classified as needing an island.
    The reduce path never relied on the fast path as an oracle — `_one_meaning`
    asks separately — and this is the model path asking too.
    """
    cg = compile_text(_ARM_AMBIGUOUS, cache_key="parity-arm-pda")
    with pytest.raises((UnsupportedConstructError, PdaFail)):
        pda_model(prod(cg).pda, "#ab", cg.fold)


def test_an_arm_choice_is_refused_by_both_engines_not_answered_differently() -> None:
    """Neither engine may quietly pick when the arms mean different things.

    This is vyx's divergence in four lines, without vyx's tokenizer. Before the
    fix the two paths disagreed in silence — Earley folded `Plain('#ab')` and
    the PDA folded `Forced('#ab')` — because `earley_model` goes through
    `parse_first` (deterministic under ambiguity by design) while only the
    reduce path asked `_one_meaning`. Two engines each picking "the first"
    derivation are not picking the same one.

    A split has a defined answer and is not covered here; `is_arm_choice`
    separates the two, and this input is on the refusing side of it.

    Both sides call the real MODEL entries. `forced_engine` is deliberately not
    used: it hand-rolls `parse_first` + fold, and `parse_first` returns a tree
    with no fold to build values from, so it cannot answer a question about
    meanings and does not gate. That second route is the same two-entries shape
    the PDA half had — worth knowing about, not worth asserting here.
    """
    cg = compile_text(_ARM_AMBIGUOUS, cache_key="parity-arm-ambiguous")
    pr = product = prod(cg)
    outcomes: dict[str, object] = {}
    for label, call in (
        (
            "earley",
            lambda: earley_model(pr.instance_grammar, "#ab", cg.fold, pr.tables),
        ),
        ("pda", lambda: pda_model(product.pda, "#ab", cg.fold)),
    ):
        try:
            outcomes[label] = call()
        except UnsupportedConstructError, PdaFail:
            outcomes[label] = REFUSED
    assert outcomes["earley"] is REFUSED and outcomes["pda"] is REFUSED, (
        "an ambiguous arm choice must be refused by both engines, not answered "
        f"differently: {outcomes}"
    )


REFUSED = object()
"""Sentinel for "this engine declined", distinct from any model it could build."""
