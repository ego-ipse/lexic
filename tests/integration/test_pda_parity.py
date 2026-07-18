"""Differential CI: PDA vs engine, across all 10 ground-truth grammars (Task 7).

Where :mod:`tests.unit.lexic.parsing.pda.test_runtime` scopes its parity gate to
the four **island-free** grammars, this module is the *wide* matrix: all 10
ground-truth grammars (islands included — c/chess/json/json_arr/json_ws all
carry at least one), each driven through both internal seams directly:

- **forced-PDA** — :func:`~lexic.parsing.pda.runtime.runtime.parse_pda` with the real
  fold supplied (so island references splice their Earley sub-parse);
- **forced-engine** — ``cg.fold.apply(parse_first(_prod(cg).instance_grammar, text,
  _prod(cg).tables))``, the same call :meth:`~lexic.compile.CompiledGrammar.parse`'s
  fallback branch makes.

The correctness bar is ruling 1 (semantic parity, not raw ``dump()``
equality — the PDA's greedy stop-set loop may split a ``semantic=False`` run
differently from the engine's ambiguity resolution): every sample where both
paths succeed asserts deep semantic equality (:func:`_deep_semantic` —
``semantic=False`` binds dropped at every level) plus a ``to_text()``
round-trip on *both* models. A forced-PDA ``PdaFail`` is a **fallback**, not a
failure — it is tallied, not asserted against (except that the engine path
alone must still round-trip). The raw ``dump()``-exact rate and the
fallback rate are *reported* (printed) per grammar, not gated — they feed the
effort's OUTCOME numbers, not a pass/fail bar.
"""

from __future__ import annotations

import random
from typing import cast

import pytest

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
from lexic.model import GrammarModel
from lexic.parsing import parse_first
from lexic.parsing.pda.compiler.clones import KTupleGate, PeekGate
from lexic.parsing.pda.compiler.flatten import all_clones
from lexic.parsing.pda.compiler.specs import IslandRef
from lexic.parsing.pda.runtime.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import _model_product
from tests.paths import ABNF_GRAMMARS, GBNF_GRAMMARS, GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.test_runtime import _arithmetic_bench_corpus


def _prod(cg):
    """The instance product for a CompiledGrammar — pda / instance_grammar / tables
    (memoised per (grammar, fold); the artefact no longer carries them)."""
    return _model_product(cg.codegen_grammar, cg.fold)


# ── fixtures ────────────────────────────────────────────────────────────

# The wide matrix: every GBNF ground-truth grammar bar vyx (whose non-default
# @start corpus is exercised elsewhere) plus both ABNF grammars.
_ALL_STEMS: tuple[str, ...] = (
    *(g for g in GBNF_GRAMMARS if g != "vyx.gbnf"),
    *ABNF_GRAMMARS,
)
_N_SEEDS = 40
_MAX_DEPTH = 4

# A couple of representative bench-shaped corpora. Arithmetic's is imported
# from test_runtime.py (its own bench-corpus test already pins the same
# snippets/target length — reusing it, not re-pinning the literal, sidesteps
# the whole-tree pylint R0801 duplicate-code gate). json's mirrors
# tools/benchmark/pipeline_bench.py's ``_JSON_ITEMS``/``_json_corpus`` (same
# items, same target length) — pinned locally since nothing else in the test
# tree defines it yet; not imported from the benchmark module itself (the
# same "not a code donor for tests" precedent test_runtime.py set).
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
        super().__init__(checked=0, pda_ok=0, fallback=0, engine_only=0, dump_exact=0)


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
    tree = parse_first(_prod(cg).instance_grammar, text, _prod(cg).tables)
    return cast(GrammarModel, cg.fold.apply(tree))


def _deep_semantic(value: object) -> object:
    """The ruling-1 comparator: drop ``semantic=False`` binds at EVERY level.

    ``semantic_dump()``'s exclusion is top-level-only (R2-5); the prior
    declared-schema dump's erasure (F-DUMP-1) happened to hide nested noise
    splits too, so ``semantic_dump()`` equality *looked* like the ruling-1
    bar. The runtime-complete native dump exposes those nested
    ``semantic=False`` fields, so the noise split the PDA is licensed to
    make differently (see the module docstring) must be dropped explicitly,
    at every model level, before comparing.
    """
    if isinstance(value, GrammarModel):
        return {
            name: _deep_semantic(getattr(value, name)) for name in value.semantic_dump()
        }
    if isinstance(value, tuple):
        return [_deep_semantic(sub) for sub in value]
    return value


def _check_one(cg: CompiledGrammar, text: str, tally: _Tally) -> None:
    """Run both seams on ``text``, tally the outcome, assert what parity demands.

    :raises UnsupportedConstructError: Propagated from the engine path on a
        generator-overshoot input the grammar itself rejects — the caller
        skips the sample rather than counting it.
    """
    engine_model = _forced_engine(cg, text)
    assert engine_model.to_text() == text
    if isinstance(_prod(cg).pda.start_key, IslandRef):
        tally["checked"] += 1
        tally["engine_only"] += 1
        return
    try:
        pda_model = cast(GrammarModel, parse_pda(_prod(cg).pda, text, cg.fold))
    except PdaFail:
        tally["fallback"] += 1
        tally["checked"] += 1
        return
    tally["pda_ok"] += 1
    tally["checked"] += 1
    assert _deep_semantic(pda_model) == _deep_semantic(engine_model)
    assert pda_model.to_text() == text
    if pda_model.dump() == engine_model.dump():
        tally["dump_exact"] += 1


def _report(stem: str, cg: CompiledGrammar, tally: _Tally) -> None:
    """Print the per-grammar summary line (reported, not asserted)."""
    n = tally["checked"] or 1
    if isinstance(_prod(cg).pda.start_key, IslandRef):
        print(
            f"{stem:16s} checked={tally['checked']:3d} ENGINE-ONLY (whole-grammar PDA opt-out)"
        )
        return
    islands = sorted(_prod(cg).pda.islands)
    exact = (
        f"{tally['dump_exact'] / tally['pda_ok']:5.1%}" if tally["pda_ok"] else "n/a"
    )
    print(
        f"{stem:16s} checked={tally['checked']:3d} "
        f"pda_ok={tally['pda_ok']:3d} "
        f"fallback_rate={tally['fallback'] / n:5.1%} "
        f"dump_exact_rate={exact} "
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


# ── P2 k-window demotion — the anti-trap gates (Task 6.3 part c) ──────────
#
# Island-move + byte-parity alone are insufficient here: a demoted decision
# compiled with an empty/wrong gate would mis-parse → PdaFail → engine
# fallback, so both gates would PASS while the PDA is unsound AND slower
# (task63fix finding F2). These tests therefore drive the demoted decisions
# through ``parse_pda`` directly — a ``PdaFail`` IS a failure, no fallback
# masks a wrong gate — and pin the gates' structural presence.

_CHESS_ADVERSARIAL: tuple[str, ...] = (
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
    assert not isinstance(_prod(cg).pda.start_key, IslandRef)
    assert sorted(_prod(cg).pda.islands) == []
    nonpawn = [
        spec for key, spec in _prod(cg).pda.clones.items() if key.name == "nonpawn"
    ]
    assert nonpawn, "nonpawn must be cloned now (demoted, not islanded)"
    assert any(
        isinstance(item.gate, KTupleGate)
        for spec in nonpawn
        for arm in spec.arms
        for item in arm.specs
    ), "the demoted nonpawn loop must carry a k-window gate"
    for text in _CHESS_ADVERSARIAL:
        pda_model = cast(GrammarModel, parse_pda(_prod(cg).pda, text, cg.fold))
        engine_model = _forced_engine(cg, text)
        assert _deep_semantic(pda_model) == _deep_semantic(engine_model)
        assert pda_model.to_text() == text


def test_p2_lo_gt_k_arm_gate_is_eof_exact_end_to_end() -> None:
    """The ``lo > k`` → k=3 digit-vs-EOF arm separation (the re-bless hard
    constraint) exercised through the real compiled runtime: selecting
    ``"12"`` requires the EOF-carrying window position to match exactly at
    end-of-input, never a generic character."""
    cg = compile_text(
        'root ::= [0-9]{4,} "x" | "12"\n', flavour="gbnf", cache_key="p2-lo-gt-k-eof"
    )
    assert not isinstance(_prod(cg).pda.start_key, IslandRef)
    assert not _prod(cg).pda.islands
    clones = all_clones([_prod(cg).pda.program.start])
    assert any(clone.kwin_selectors is not None for clone in clones), (
        "the demoted alternation must select by k-window"
    )
    assert cast(GrammarModel, parse_pda(_prod(cg).pda, "12", cg.fold)).to_text() == "12"
    for text in ("1234x", "1234567x"):
        assert (
            cast(GrammarModel, parse_pda(_prod(cg).pda, text, cg.fold)).to_text()
            == text
        )
    with pytest.raises(PdaFail):
        parse_pda(
            _prod(cg).pda, "123x", cg.fold
        )  # 3 digits < lo=4 — in no arm's language


# ── P3 noise-skip peek — the anti-trap gates (Task 6.4) ────────────────────

_JSON_ADVERSARIAL: tuple[str, ...] = (
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
    PDA — driven through ``parse_pda`` directly, so a wrong peek gate fails
    here rather than hiding behind the engine fallback."""
    cg = compile_from_path(GROUND_TRUTH / "json.gbnf")
    assert not isinstance(_prod(cg).pda.start_key, IslandRef)
    assert sorted(_prod(cg).pda.islands) == []
    value_clones = [s for key, s in _prod(cg).pda.clones.items() if key.name == "value"]
    assert value_clones
    assert all(arm.peek is not None for spec in value_clones for arm in spec.arms), (
        "value must select by post-noise peek"
    )
    item2 = [s for key, s in _prod(cg).pda.clones.items() if key.name == "array-item2"]
    assert item2
    assert any(
        isinstance(item.gate, PeekGate)
        for spec in item2
        for arm in spec.arms
        for item in arm.specs
    ), "the array-item loop must carry a peek gate"
    for text in _JSON_ADVERSARIAL:
        pda_model = cast(GrammarModel, parse_pda(_prod(cg).pda, text, cg.fold))
        engine_model = _forced_engine(cg, text)
        assert _deep_semantic(pda_model) == _deep_semantic(engine_model)
        assert pda_model.to_text() == text
