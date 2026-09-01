"""Tests for lexic.parsing.pda.compiler.clones — the per-(rule, continuation) clone compiler.

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

from lexic.compile import canonical_grammar, compile_from_path, compile_text
from lexic.compile.pipeline.moments import build_codegen_grammar
from lexic.grammars import GBNF_FLAVOUR, flavour_for_extension
from lexic.ir import IrAst, IrMap
from lexic.parsing.earley.kernel.tables.records import ORIGIN_BITS, ParserTables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import ModelBinding, ModelFold, lift_optional_nullables
from lexic.parsing.pda.compiler.clones import (
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
    StopGate,
    compile_pda,
)
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
)
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail, pda_model
from lexic.parsing.products import _model_product
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.analysis.test_analysis import PINNED_ISLANDS

# ── helpers ───────────────────────────────────────────────────────────────


def pda_for(path: Path) -> PdaTables:
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
        _model_product(compiled.codegen_grammar, compiled.product).instance_grammar,
        compiled.product,
    )


def only_arm(clone: FlatClone) -> FlatArm:
    """The clone's sole arm, whichever of ``selectors``/``default`` holds it.

    Every hand grammar below is small enough to compile to one FIRST-gated
    arm (or, for the dispatch-conversion negative case, one default-less
    alternation) — asserts that shape rather than silently picking one.
    """
    if clone.selectors:
        assert len(clone.selectors) == 1
        return clone.selectors[0][2]
    assert clone.default is not None
    return clone.default


def pda_from_text(text: str) -> PdaTables:
    """Compile a hand-authored GBNF snippet to its :class:`PdaTables`."""
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    lifted = lift_optional_nullables(build_codegen_grammar(canonical))
    compiled = compile_text(text, flavour="gbnf")
    return compile_pda(
        lifted,
        _model_product(compiled.codegen_grammar, compiled.product).instance_grammar,
        compiled.product,
    )


def clones_named(pda: PdaTables, name: str) -> list[CloneSpec]:
    """Every compiled clone for rule ``name``, across all its hard-continuation tails."""
    return [spec for key, spec in pda.clones.items() if key.name == name]


def sole_clone(pda: PdaTables, name: str) -> CloneSpec:
    """The one compiled clone for rule ``name`` — asserts exactly one exists."""
    specs = clones_named(pda, name)
    assert len(specs) == 1
    return specs[0]


def walk_specs(specs: Sequence[ItemSpec]) -> Iterator[ItemSpec]:
    """Yield every :class:`ItemSpec` in ``specs``, recursing into group arms."""
    for spec in specs:
        yield spec
        if spec.kind == GRP:
            group = cast(GroupSpec, spec.payload)
            for arm in group.arms:
                yield from walk_specs(arm.specs)
            if group.default is not None:
                yield from walk_specs(group.default)


def all_specs(pda: PdaTables) -> Iterator[ItemSpec]:
    """Yield every :class:`ItemSpec` across every clone in ``pda``."""
    for clone in pda.clones.values():
        for arm in clone.arms:
            yield from walk_specs(arm.specs)
        if clone.default is not None:
            yield from walk_specs(clone.default)


# ── the headline gate (pinned to the plan's Task-3 ledger line) ───────────

# The noun is one compiled ``CloneSpec`` entry keyed by (rule, hard tail).
# Generated repeat loopback is not a hard tail, so it creates no extra entry.
PINNED_CLONE_COUNTS: dict[str, int] = {
    "arithmetic.gbnf": 22,
    "c.gbnf": 60,  # +1: relationoperator demotes (group arm gate) and clones
    "chess.gbnf": 10,  # +2 at P2: nonpawn demoted from island → cloned (k-gate)
    "japanese.gbnf": 7,
    "json.gbnf": 87,  # island-free at P3: the whole grammar clones
    "json_arr.gbnf": 26,  # +2: number attempts (group arms) and clones
    "json_ws.gbnf": 25,  # +2: the json_arr twin, same group
    "list.gbnf": 2,
    "arithmetic.abnf": 7,
    "json.abnf": 87,  # the GBNF twin, also island-free at P3
}

ALL_STEMS: tuple[str, ...] = tuple(sorted(PINNED_CLONE_COUNTS))
"""The pinned island sets are single-homed in ``test_analysis`` (this module's
gate is the *clone compiler*, not the island computation itself — re-pinning
the same literal here would be both redundant coverage and R0801 bait)."""


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_compiles_clean_for_every_ground_truth(stem: str):
    """compile_pda succeeds (no raise) on every ground-truth grammar."""
    pda = pda_for(GROUND_TRUTH / stem)
    assert isinstance(pda, PdaTables)
    assert isinstance(pda.start_key, (CloneKey, IslandRef))
    assert isinstance(pda.instance_grammar, IrAst)


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_clone_count_matches_pinned(stem: str):
    """The compiled clone count matches the pinned, coordinator-verified value."""
    pda = pda_for(GROUND_TRUTH / stem)
    assert len(pda.clones) == PINNED_CLONE_COUNTS[stem]


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_no_pending_placeholder_leaks(stem: str):
    """Every clone's own name matches its key's — no in-progress placeholder remains.

    ``ensure_rule`` reserves a clone key with a ``_PENDING`` sentinel (empty
    name) before compiling the body; a real rule is never named ``""``, so a
    name/key mismatch (or an empty name) would mean a placeholder leaked.
    """
    pda = pda_for(GROUND_TRUTH / stem)
    for key, spec in pda.clones.items():
        assert spec.name == key.name
        assert spec.name


PINNED_RESIDUE: dict[str, list[str]] = {stem: [] for stem in PINNED_ISLANDS}
"""The compiler-level island RESIDUE — the analysis' islands minus the
attemptable set (which clones instead). **Every ground-truth grammar is now
island-free here.** `c.gbnf`'s five went first (four always attempted;
group-arm k-window demotion took `relationoperator`), and ordered attempt on
group arms took the last two: `json_arr`/`json_ws`'s `number`, whose
`number[1]grp` overlap no fixed-k window separates. The island machinery is
still reachable — left recursion is the residue no licence can settle — but no
shipped grammar reaches it."""


@pytest.mark.parametrize("stem", sorted(PINNED_RESIDUE))
def test_island_set_matches_pinned(stem: str):
    """The compiled island residue matches the pinned value."""
    pda = pda_for(GROUND_TRUTH / stem)
    assert sorted(pda.islands) == PINNED_RESIDUE[stem]


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_island_rules_are_never_cloned(stem: str):
    """No CloneKey ever names an island rule — islands opt out of cloning entirely."""
    pda = pda_for(GROUND_TRUTH / stem)
    for key in pda.clones:
        assert key.name not in pda.islands


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_refs_carry_islandref_iff_their_target_is_an_island(stem: str):
    """A ``ref`` spec's payload is an IslandRef exactly when its target is an island.

    Every other ``ref`` spec resolves to a :class:`CloneKey` naming a
    non-island rule — the two payload shapes never cross.
    """
    pda = pda_for(GROUND_TRUTH / stem)
    for spec in all_specs(pda):
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
    pda = pda_for(GROUND_TRUTH / "arithmetic.gbnf")
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
    pda = pda_for(GROUND_TRUTH / "json.gbnf")
    assert "ws" not in pda.islands
    ws_clones = clones_named(pda, "ws")
    assert ws_clones
    for clone in ws_clones:
        gate = clone.arms[0].specs[0].gate
        assert isinstance(gate, StopGate)
        assert gate.charset == CharSet.from_chars(" ", "\t", "\n", "\r")
    assert not any(
        spec.kind == REF and spec.payload == IslandRef("ws") for spec in all_specs(pda)
    )


# ── small hand-grammar shapes ───────────────────────────────────────────────


def test_hand_grammar_optional_literal_gets_pair_gate_on_ll2_discriminator():
    """``"fx"? "f1"`` — the chess ``fxf5``/``f5`` shape — compiles to a
    PairGate: FIRST(``"fx"``) overlaps FIRST(``"f1"``) on the leading char,
    but the second char discriminates.
    """
    pda = pda_from_text('root ::= "fx"? "f1"\n')
    root = sole_clone(pda, "root")
    fx_spec = root.arms[0].specs[0]
    assert fx_spec.kind == LIT
    assert fx_spec.payload == "fx"
    assert isinstance(fx_spec.gate, PairGate)
    assert fx_spec.gate.pairs == frozenset({"fx"})


def test_hand_grammar_unbounded_negated_charclass_gets_stopgate():
    """An unbounded ``[^"]*`` loop with no FIRST/continuation overlap stays a
    plain non-greedy StopGate.
    """
    pda = pda_from_text('root ::= [^"]* "\\""\n')
    root = sole_clone(pda, "root")
    loop_spec = root.arms[0].specs[0]
    assert loop_spec.kind == CC
    assert isinstance(loop_spec.gate, StopGate)


def test_hand_grammar_ref_to_a_genuine_island_carries_islandref():
    """``x ::= x "a" | "b"`` is LEFT-RECURSIVE — the island class no attempt
    order can settle (the unbounded digit-prefix overlap shape it replaces now
    legitimately attempts), so ``x`` is flagged an island, and a ref to it from
    ``root`` carries an :class:`IslandRef`, never a :class:`CloneKey`.
    """
    pda = pda_from_text('root ::= x\nx ::= x "a" | "b"\n')
    assert pda.islands == frozenset({"x", "x-arm1"})  # the hoisted arm too
    root = sole_clone(pda, "root")
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
    :func:`~lexic.parsing.pda.runtime.kernel.kernel.pda_model` refuses
    ("ab" and "cab") with a
    :exc:`~lexic.parsing.pda.runtime.kernel.kernel.PdaFail` (→ engine fallback) rather than
    returning the wrong model.
    """
    text = 'root ::= x "ab"?\nx ::= [a-c]*\n'
    pda = pda_from_text(text)
    assert "x" in pda.islands
    root = sole_clone(pda, "root")
    ref_spec = root.arms[0].specs[0]
    assert ref_spec.kind == REF
    assert ref_spec.payload == IslandRef("x", fail=True)

    lifted = lift_optional_nullables(
        build_codegen_grammar(canonical_grammar(text, GBNF_FLAVOUR))
    )
    live = compile_pda(
        lifted, normalize(lifted), compile_text(text, flavour="gbnf").product
    )
    for inp in ("ab", "cab"):
        with pytest.raises(PdaFail):
            pda_model(live, inp)


def test_hand_grammar_value_str_rule_clone_is_match_only():
    """A rule with no rule-refs anywhere in its body (``value_str``) is
    flagged ``match_only`` — its interior is pure-terminal, no sub-models
    to build below it.
    """
    pda = pda_from_text('root ::= lit\nlit ::= "a" | "b"\n')
    lit_specs = clones_named(pda, "lit")
    assert lit_specs
    assert all(spec.match_only for spec in lit_specs)


def test_hand_grammar_empty_alternation_arm_becomes_the_default_not_a_gated_arm():
    """An all-nullable empty arm (FIRST is empty) never gates as an ArmSpec —
    it becomes the clone's default arm instead (``compile_arms``'s
    "empty arm never gates" rule).
    """
    pda = pda_from_text('root ::= opt "z"\nopt ::= "a" | ""\n')
    opt = sole_clone(pda, "opt")
    assert len(opt.arms) == 1
    assert opt.default == ()


# ── island_tables memoisation ────────────────────────────────────────────


def test_island_tables_is_memoised_per_island_rule():
    """island_tables(name) returns the identical ParserTables object on repeat calls.

    Driven from a LEFT-RECURSIVE grammar rather than a ground-truth file: no
    shipped grammar islands any more (ordered attempt now settles the last of
    them, `json_arr`/`json_ws`'s `number`), and left recursion is the one
    residue no gate or attempt can license — no arm order helps a rule that
    re-enters at the same position.
    """
    pda = pda_from_text('root ::= e\ne ::= e "+" e | "a"\n')
    name = next(iter(pda.islands))
    first = pda.island_tables(name)
    second = pda.island_tables(name)
    assert first is second
    assert isinstance(first, ParserTables)


# ── depth safety: the ensure_rule drain (L7, clone-compiler half) ──────


def test_long_ref_chain_compiles_at_constant_stack_depth():
    """A 300-rule unit-ref chain compiles without RecursionError.

    ``ensure_rule`` used to recurse one Python frame set per chained rule
    (``compile_arms`` → ``_spec_ruleref`` → ``ensure_rule``); the outermost
    call now drains a work queue, so chain length no longer consumes stack.
    Every queued clone is complete on return (no ``_PENDING`` residue).
    """
    depth = 300
    lines = [f'r{i} ::= "[" r{i + 1} "]"' for i in range(depth)]
    lines.append(f'r{depth} ::= "0"')
    grammar = "\n".join(lines) + "\n"
    lifted = lift_optional_nullables(
        build_codegen_grammar(canonical_grammar(grammar, GBNF_FLAVOUR))
    )
    pda = compile_pda(lifted, normalize(lifted), ModelBinding(ModelFold(IrMap())))
    assert isinstance(pda.start_key, CloneKey)
    assert all(spec.name for spec in pda.clones.values())  # no _PENDING left


# ── island tables inherit the run's packing tier ─────────────────────────


def test_island_tables_cache_per_name_and_tier():
    """island_tables(name, bits) compiles at the requested tier, caches per
    (name, bits), and keeps tiers distinct."""
    pda = pda_from_text('root ::= "a" "b"\n')
    small = pda.island_tables("root", 8)
    assert small.packing.bits == 8
    assert pda.island_tables("root", 8) is small
    default = pda.island_tables("root")
    assert default is not small
    assert default.packing.bits == ORIGIN_BITS


def test_island_follow_carries_a_charset_per_island():
    """Every island name keys a follow CharSet holding what can follow it —
    the continuation evidence the island seam's cross-span check reads. The
    fixture islands by LEFT RECURSION (the cross-span overlap shape it
    replaces now attempts instead of islanding)."""
    pda = pda_from_text('root ::= item "e"\nitem ::= item "d" | "a"\n')
    assert "item" in pda.islands
    assert set(pda.island_follow) == set(pda.islands)
    follow = pda.island_follow["item"]
    assert follow.has("d") and follow.has("e")
    assert not follow.has("z")
