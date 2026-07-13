"""Tests for lexic.parsing.pda.clones — the per-(rule, continuation) clone compiler.

The headline gate pins, per ground-truth grammar, the exact clone count and
island set :func:`compile_pda` must produce (byte-matched against the
hybrid-parsing PoC's milestone-3 output — see the plan's Task-3 ledger line).
The remaining sections prove the island/clone dedup invariants that make the
clone table meaningful (islands never cloned, refs to them always carry
:class:`IslandRef`, no in-progress placeholder survives), the pivot-4/6 gate
shapes on the arithmetic ``ws`` / json ``ws`` fixtures named in the plan, and
the small hand-grammar shapes (LL(2) pair gate, stop-set, island ref,
``value_str``/``match_only``, empty-arm-as-default) that are easiest to see in
isolation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Sequence, cast

import pytest

from lexic.codegen import build_codegen_grammar
from lexic.compile import canonical_grammar, compile_from_path, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR, flavour_for_extension
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import IrAst
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import Reducer
from lexic.parsing.earley.tables import ParserTables
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.clones import (
    CC,
    GRP,
    LIT,
    REF,
    CloneKey,
    CloneSpec,
    GroupSpec,
    IslandRef,
    ItemSpec,
    PairGate,
    PdaTables,
    ReduceRun,
    StopGate,
    compile_pda,
    compile_reduce_pda,
)
from lexic.parsing.pda.flatten import (
    BUILD_REDUCE,
    R_DROP,
    R_KEEP,
    R_SPLICE,
    FlatClone,
    all_clones,
)
from lexic.parsing.pda.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime import PdaFail
from lexic.parsing.products import _model_product
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.test_analysis import _PINNED_ISLANDS

# ── helpers ───────────────────────────────────────────────────────────────


def _pda_for(path: Path) -> PdaTables:
    """Compile a ground-truth grammar file to its :class:`PdaTables`.

    Drives the same inputs :func:`~lexic.compile._compile_core` builds,
    entirely through public seams: ``lifted`` from ``canonical_grammar`` +
    ``build_codegen_grammar`` + ``lift_optional_nullables``, and
    ``instance_grammar``/``fold_config`` read off the already-compiled
    :class:`~lexic.compile.CompiledGrammar` (``compile_from_path`` is
    memoised, so this reuses whatever other tests already built).
    """
    flavour = flavour_for_extension(path)
    canonical = canonical_grammar(path.read_text(encoding="utf-8"), flavour)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    compiled = compile_from_path(path)
    return compile_pda(
        lifted,
        _model_product(compiled.codegen_grammar, compiled.fold).instance_grammar,
        compiled.fold.config,
    )


def _pda_from_text(text: str) -> PdaTables:
    """Compile a hand-authored GBNF snippet to its :class:`PdaTables`."""
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    compiled = compile_text(text, flavour="gbnf")
    return compile_pda(
        lifted,
        _model_product(compiled.codegen_grammar, compiled.fold).instance_grammar,
        compiled.fold.config,
    )


def _clones_named(pda: PdaTables, name: str) -> list[CloneSpec]:
    """Every compiled clone for rule ``name``, across all its hard-continuation tails."""
    return [spec for key, spec in pda.clones.items() if key.name == name]


def _sole_clone(pda: PdaTables, name: str) -> CloneSpec:
    """The one compiled clone for rule ``name`` — asserts exactly one exists."""
    specs = _clones_named(pda, name)
    assert len(specs) == 1
    return specs[0]


def _walk_specs(specs: Sequence[ItemSpec]) -> Iterator[ItemSpec]:
    """Yield every :class:`ItemSpec` in ``specs``, recursing into group arms."""
    for spec in specs:
        yield spec
        if spec.kind == GRP:
            group = cast(GroupSpec, spec.payload)
            for arm in group.arms:
                yield from _walk_specs(arm.specs)
            if group.default is not None:
                yield from _walk_specs(group.default)


def _all_specs(pda: PdaTables) -> Iterator[ItemSpec]:
    """Yield every :class:`ItemSpec` across every clone in ``pda``."""
    for clone in pda.clones.values():
        for arm in clone.arms:
            yield from _walk_specs(arm.specs)
        if clone.default is not None:
            yield from _walk_specs(clone.default)


# ── the headline gate (pinned to the plan's Task-3 ledger line) ───────────

_PINNED_CLONE_COUNTS: dict[str, int] = {
    "arithmetic.gbnf": 32,
    "c.gbnf": 15,
    "chess.gbnf": 10,  # +2 at P2: nonpawn demoted from island → cloned (k-gate)
    "japanese.gbnf": 12,
    "json.gbnf": 126,  # island-free at P3: the whole grammar clones
    "json_arr.gbnf": 36,
    "json_ws.gbnf": 35,
    "list.gbnf": 2,
    "arithmetic.abnf": 10,
    "json.abnf": 126,  # the GBNF twin, also island-free at P3
}

_ALL_STEMS: tuple[str, ...] = tuple(sorted(_PINNED_CLONE_COUNTS))
"""The pinned island sets are single-homed in ``test_analysis`` (this module's
gate is the *clone compiler*, not the island computation itself — re-pinning
the same literal here would be both redundant coverage and R0801 bait)."""


@pytest.mark.parametrize("stem", _ALL_STEMS)
def test_compiles_clean_for_every_ground_truth(stem: str):
    """compile_pda succeeds (no raise) on every ground-truth grammar."""
    pda = _pda_for(GROUND_TRUTH / stem)
    assert isinstance(pda, PdaTables)
    assert isinstance(pda.start_key, (CloneKey, IslandRef))
    assert isinstance(pda.instance_grammar, IrAst)


@pytest.mark.parametrize("stem", _ALL_STEMS)
def test_clone_count_matches_pinned(stem: str):
    """The compiled clone count matches the pinned, coordinator-verified value."""
    pda = _pda_for(GROUND_TRUTH / stem)
    assert len(pda.clones) == _PINNED_CLONE_COUNTS[stem]


@pytest.mark.parametrize("stem", _ALL_STEMS)
def test_no_pending_placeholder_leaks(stem: str):
    """Every clone's own name matches its key's — no in-progress placeholder remains.

    ``ensure_rule`` reserves a clone key with a ``_PENDING`` sentinel (empty
    name) before compiling the body; a real rule is never named ``""``, so a
    name/key mismatch (or an empty name) would mean a placeholder leaked.
    """
    pda = _pda_for(GROUND_TRUTH / stem)
    for key, spec in pda.clones.items():
        assert spec.name == key.name
        assert spec.name


@pytest.mark.parametrize("stem", sorted(_PINNED_ISLANDS))
def test_island_set_matches_pinned(stem: str):
    """The island rule set matches the pinned, coordinator-verified value."""
    pda = _pda_for(GROUND_TRUTH / stem)
    assert sorted(pda.islands) == _PINNED_ISLANDS[stem]


@pytest.mark.parametrize("stem", _ALL_STEMS)
def test_island_rules_are_never_cloned(stem: str):
    """No CloneKey ever names an island rule — islands opt out of cloning entirely."""
    pda = _pda_for(GROUND_TRUTH / stem)
    for key in pda.clones:
        assert key.name not in pda.islands


@pytest.mark.parametrize("stem", _ALL_STEMS)
def test_refs_carry_islandref_iff_their_target_is_an_island(stem: str):
    """A ``ref`` spec's payload is an IslandRef exactly when its target is an island.

    Every other ``ref`` spec resolves to a :class:`CloneKey` naming a
    non-island rule — the two payload shapes never cross.
    """
    pda = _pda_for(GROUND_TRUTH / stem)
    for spec in _all_specs(pda):
        if spec.kind != REF:
            continue
        target = spec.payload
        if isinstance(target, IslandRef):
            assert target.name in pda.islands
        else:
            assert isinstance(target, CloneKey)
            assert target.name not in pda.islands


# ── gate/stop-set correctness on named fixture shapes (pivots 2/4) ─────────


def test_arithmetic_ws_stopgate_excludes_newline_only_when_the_tail_reaches_it():
    """arithmetic's ``ws`` loop excludes ``\\n`` from its stop-set exactly when
    the clone's own hard continuation could begin with ``\\n`` (the trailing
    ``ws term "\\n"`` shape) — otherwise ``\\n`` stays in the stop-set since the
    loop may safely keep consuming it (the ``ws "=" ...`` shape, pivot 4).
    """
    pda = _pda_for(GROUND_TRUTH / "arithmetic.gbnf")
    ws_clones = [(k, s) for k, s in pda.clones.items() if k.name == "ws"]
    assert ws_clones
    saw_excluding = saw_including = False
    for key, spec in ws_clones:
        gate = spec.arms[0].specs[0].gate
        assert isinstance(gate, StopGate)
        if key.tail.has("\n"):
            assert not gate.charset.has("\n")
            saw_excluding = True
        else:
            assert gate.charset.has("\n")
            saw_including = True
        assert gate.charset.has(" ") and gate.charset.has("\t")
    assert saw_excluding and saw_including


def test_json_ws_is_cloned_with_a_greedy_whitespace_stopgate():
    """json's ``ws`` is CLONED under the P6 noise-greedy licence, not islanded.

    Its ``[ \\t\\n\\r]*`` loop still runs up to a *soft-only* whitespace
    follower (``value ws`` abutting ``value-separator ::= ws "," ws``) — but
    ``ws`` is ``semantic=False``, no hard follower is whitespace-led, and no
    whitespace can follow it as semantic content, so the greedy over-eat is
    noise↔noise (the split between adjacent ``ws`` fields moves; bytes and
    ``semantic_dump`` do not). Every ``ws`` clone bakes the plain greedy
    whitespace :class:`StopGate` (its hard tails carry no whitespace, so
    nothing is subtracted).
    """
    pda = _pda_for(GROUND_TRUTH / "json.gbnf")
    assert "ws" not in pda.islands
    ws_clones = _clones_named(pda, "ws")
    assert ws_clones
    for clone in ws_clones:
        gate = clone.arms[0].specs[0].gate
        assert isinstance(gate, StopGate)
        assert gate.charset == CharSet.from_chars(" ", "\t", "\n", "\r")
    assert not any(
        spec.kind == REF and spec.payload == IslandRef("ws") for spec in _all_specs(pda)
    )


# ── small hand-grammar shapes ───────────────────────────────────────────────


def test_hand_grammar_optional_literal_gets_pair_gate_on_ll2_discriminator():
    """``"fx"? "f1"`` — the chess ``fxf5``/``f5`` shape — compiles to a
    PairGate: FIRST(``"fx"``) overlaps FIRST(``"f1"``) on the leading char,
    but the second char discriminates.
    """
    pda = _pda_from_text('root ::= "fx"? "f1"\n')
    root = _sole_clone(pda, "root")
    fx_spec = root.arms[0].specs[0]
    assert fx_spec.kind == LIT
    assert fx_spec.payload == "fx"
    assert isinstance(fx_spec.gate, PairGate)
    assert fx_spec.gate.pairs == frozenset({"fx"})


def test_hand_grammar_unbounded_negated_charclass_gets_stopgate():
    """An unbounded ``[^"]*`` loop with no FIRST/continuation overlap stays a
    plain non-greedy StopGate.
    """
    pda = _pda_from_text('root ::= [^"]* "\\""\n')
    root = _sole_clone(pda, "root")
    loop_spec = root.arms[0].specs[0]
    assert loop_spec.kind == CC
    assert isinstance(loop_spec.gate, StopGate)


def test_hand_grammar_ref_to_a_genuine_island_carries_islandref():
    """``x ::= n "x" | n "y"`` shares an unbounded digit prefix across arms —
    ungatable at any ``k ≤ 3`` (the old ``"a"? "a"`` fixture now legitimately
    demotes under P2), so ``x`` is flagged an island, and a ref to it from
    ``root`` carries an :class:`IslandRef`, never a :class:`CloneKey`.
    """
    pda = _pda_from_text('root ::= x\nx ::= n "x" | n "y"\nn ::= [0-9]+\n')
    assert pda.islands == frozenset({"x"})
    root = _sole_clone(pda, "root")
    ref_spec = root.arms[0].specs[0]
    assert ref_spec.kind == REF
    assert ref_spec.payload == IslandRef("x")


def test_hand_grammar_loop_over_soft_only_follower_islands_and_refuses():
    """``root ::= x "ab"?`` / ``x ::= [a-c]*`` — the F1 silent-wrong-model shape.

    ``x``'s trailing ``[a-c]*`` loop runs up to ``x``'s FOLLOW, which at the
    ``root`` call site includes the *optional* ``"ab"?``'s ``'a'``. That ``'a'``
    is a soft-only follower absent from ``x``'s hard clone tail (``{""}``), so a
    non-greedy stop-set would greedily eat it — ``x`` must island. Islanding
    routes the ref through an :class:`IslandRef`, so the pure-PDA
    :func:`~lexic.parsing.pda.runtime.parse_pda` refuses ("ab" and "cab") with a
    :exc:`~lexic.parsing.pda.runtime.PdaFail` (→ engine fallback) rather than
    returning the wrong model.
    """
    text = 'root ::= x "ab"?\nx ::= [a-c]*\n'
    pda = _pda_from_text(text)
    assert "x" in pda.islands
    root = _sole_clone(pda, "root")
    ref_spec = root.arms[0].specs[0]
    assert ref_spec.kind == REF
    assert ref_spec.payload == IslandRef("x", fail=True)

    lifted = lift_optional_nullables(
        build_codegen_grammar(canonical_grammar(text, GBNF_FLAVOUR))
    )
    live = compile_pda(
        lifted, normalize(lifted), compile_text(text, flavour="gbnf").fold.config
    )
    for inp in ("ab", "cab"):
        with pytest.raises(PdaFail):
            parse_pda(live, inp)


def test_hand_grammar_value_str_rule_clone_is_match_only():
    """A rule with no rule-refs anywhere in its body (``value_str``) is
    flagged ``match_only`` — its interior is pure-terminal, no sub-models
    to build below it.
    """
    pda = _pda_from_text('root ::= lit\nlit ::= "a" | "b"\n')
    lit_specs = _clones_named(pda, "lit")
    assert lit_specs
    assert all(spec.match_only for spec in lit_specs)


def test_hand_grammar_empty_alternation_arm_becomes_the_default_not_a_gated_arm():
    """An all-nullable empty arm (FIRST is empty) never gates as an ArmSpec —
    it becomes the clone's default arm instead (``compile_arms``'s
    "empty arm never gates" rule).
    """
    pda = _pda_from_text('root ::= opt "z"\nopt ::= "a" | ""\n')
    opt = _sole_clone(pda, "opt")
    assert len(opt.arms) == 1
    assert opt.default == ()


# ── island_tables memoisation ────────────────────────────────────────────


def test_island_tables_is_memoised_per_island_rule():
    """island_tables(name) returns the identical ParserTables object on repeat calls."""
    pda = _pda_for(GROUND_TRUTH / "json_arr.gbnf")  # json itself is island-free now
    name = next(iter(pda.islands))
    first = pda.island_tables(name)
    second = pda.island_tables(name)
    assert first is second
    assert isinstance(first, ParserTables)


# ── compile_reduce_pda (b1 grammar-text path) ───────────────────────────


def _reduce_pda_for(flavour: IrFlavour) -> PdaTables:
    """Compile ``flavour``'s self-grammar reduce PDA directly.

    The b1 twin of :func:`_pda_for`, bypassing :mod:`lexic.compile`'s cache:
    :func:`~lexic.compile.self_grammar_pda` composes exactly this, plus the
    whole-grammar-opt-out-to-``None`` conversion — see ``test_compile.py``
    for that seam.
    """
    reducer = flavour.reducer
    if not isinstance(reducer, Reducer):
        raise UnsupportedConstructError(f"{flavour.name!r} carries no parse Reducer")
    lifted = lift_optional_nullables(flavour.grammar)
    instance_grammar = normalize(lifted)
    return compile_reduce_pda(lifted, instance_grammar, reducer)


def test_compile_reduce_pda_builds_a_reduce_pda_for_the_gbnf_self_grammar():
    """compile_reduce_pda succeeds on GBNF's own self-grammar and sets .reduce
    to a ReduceRun bundling the flavour's own reducer."""
    pda = _reduce_pda_for(GBNF_FLAVOUR)
    assert isinstance(pda, PdaTables)
    assert isinstance(pda.reduce, ReduceRun)
    assert pda.reduce.reducer is GBNF_FLAVOUR.reducer


def test_compile_reduce_pda_gbnf_start_rule_is_a_clone_not_an_island():
    """GBNF's start rule ("grammar") is not itself an island — the start key
    is a real CloneKey the predictive runtime can enter directly."""
    pda = _reduce_pda_for(GBNF_FLAVOUR)
    assert isinstance(pda.start_key, CloneKey)
    assert pda.start_key.name == "grammar"


def test_compile_reduce_pda_abnf_start_rule_is_a_clone_not_an_island():
    """ABNF's start rule ("rulelist") is a real clone since the Task-6.6
    boundary-shift left-factor (``filler* rule rl-cont* c-wsp* c-nl?``) — the
    start key is a CloneKey the predictive runtime can enter directly (before
    the factor it was the last ABNF island, the whole-grammar opt-out)."""
    pda = _reduce_pda_for(ABNF_FLAVOUR)
    assert isinstance(pda.start_key, CloneKey)
    assert pda.start_key.name == "rulelist"


def test_every_reduce_clone_is_baked_build_reduce_never_a_model_mode():
    """reduce_rewrite retargets every reachable clone (named rule + inline
    group) to BUILD_REDUCE with a well-formed reduce_kind — the reduce
    target skips the model-specific optimizer passes entirely.
    """
    pda = _reduce_pda_for(GBNF_FLAVOUR)
    start = pda.program.start
    assert isinstance(start, FlatClone)  # not an IslandRef opt-out
    for clone in all_clones([start]):
        assert clone.mode == BUILD_REDUCE
        assert clone.reduce_kind in (R_KEEP, R_DROP, R_SPLICE)
        assert clone.needs_ends is True


# The unit-level reduce_rewrite/_bake_reduce tests live in test_reduce_pda.py
# (the functions moved there with the option-(a) rebuild, 2026-07-11).
