"""Tests for lexic.parsing.pda.compiler.clones — the per-(rule, continuation) clone compiler.

The headline gate pins, per ground-truth grammar, the exact clone count and
island set :func:`compile_pda` must produce (byte-matched against the
hybrid-parsing PoC's milestone-3 output — see the plan's Task-3 ledger line).
The remaining sections prove the island/clone dedup invariants that make the
clone table meaningful (islands never cloned, refs to them always carry
:class:`IslandRef`, no in-progress placeholder survives), the pivot-4/6 gate
shapes on the arithmetic ``ws`` / json ``ws`` fixtures named in the plan, and
the small hand-grammar shapes (window gate, stop-set, island ref,
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
from lexic.ir import IrAst
from lexic.parsing.earley.kernel.tables.records import ORIGIN_BITS, ParserTables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.lift import lift_optional_nullables
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
    KTupleGate,
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
def test_every_named_clones_completion_is_an_in_bounds_range_of_its_own_rule(
    stem: str,
):
    """Every named clone's routine names an in-bounds range of the SAME
    grammar's own verified program — the range a clone was baked from is
    one the program's own table actually declares, not a stale or
    cross-grammar index."""
    pda = pda_for(GROUND_TRUTH / stem)
    compiled = compile_from_path(GROUND_TRUTH / stem)
    completions = compiled.product.program.completions
    checked = 0
    for spec in pda.clones.values():
        if spec.routine is None:
            continue
        assert 0 <= spec.routine.completion < len(completions), spec.name
        checked += 1
    assert checked  # every named clone in the corpus has SOME routine


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
        spec.kind == REF
        and isinstance(spec.payload, IslandRef)
        and spec.payload.name == "ws"
        for spec in all_specs(pda)
    )


# ── small hand-grammar shapes ───────────────────────────────────────────────


def test_hand_grammar_optional_literal_gets_a_window_gate_on_its_second_char():
    """``"fx"? "f1"`` — the chess ``fxf5``/``f5`` shape — compiles to a window.

    FIRST(``"fx"``) overlaps FIRST(``"f1"``) on the leading character and the
    second one discriminates. This used to be a dedicated 2-character prefix
    gate; the k-window settles the same decision at ``k = 2``, because its
    prefixes are kept PER DERIVATION rather than merged into one positionwise
    box — a set of per-alternative windows discriminates exactly as a set of
    concrete 2-character strings does.
    """
    pda = pda_from_text('root ::= "fx"? "f1"\n')
    root = sole_clone(pda, "root")
    fx_spec = root.arms[0].specs[0]
    assert fx_spec.kind == LIT
    assert fx_spec.payload == "fx"
    assert isinstance(fx_spec.gate, KTupleGate)
    assert all(len(one) == 2 for one in fx_spec.gate.windows)
    assert sorted("".join(sorted(cs.chars)) for cs in fx_spec.gate.windows[0]) == [
        "f",
        "x",
    ]


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
    assert isinstance(ref_spec.payload, IslandRef)
    assert (ref_spec.payload.name, ref_spec.payload.fail) == ("x", False)


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
    assert isinstance(ref_spec.payload, IslandRef)
    assert (ref_spec.payload.name, ref_spec.payload.fail) == ("x", True)

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
    pda = compile_pda(lifted, normalize(lifted), ModelExecutable())
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


def test_an_island_refs_continuation_excludes_the_islands_own_recursion():
    """``root ::= item "e"`` / ``item ::= item "d" | "a"`` — the evidence is ``e``.

    The seam's two-ends check asks whether a SHORTER completion could compose
    with the caller, so its evidence is what the island's REFERENCES are
    followed by. ``d`` is not that: the island rule's own arm puts ``item``
    before ``"d"``, so a shorter end followed by ``d`` is the island
    continuing ITSELF, which longest-match absorbs under the same arm. This
    used to read the island rule's FOLLOW, which holds both — and so every
    left-recursive island with an infix operator refused on its first
    completion, every time, and the whole document fell back to Earley.
    """
    specs = specs_from_text('root ::= item "e"\nitem ::= item "d" | "a"\n')
    assert "item" in specs.islands
    cont = specs.occurrence_follow("item")
    assert cont.has("e"), "the caller's continuation is the evidence"
    assert not cont.has("d"), "the island's own recursion is not the caller"
    assert not cont.has("z")


def test_an_island_refs_continuation_unions_every_reference_site():
    """Two arms reach the island, and the union is what the seam must ask.

    The PDA commits to ONE of the caller's arms before entering the island, so
    asking only the entered site's continuation answers a cross-arm ambiguity
    silently. ``a+b\n`` under this grammar really does derive two ways — the
    union is what refuses it.
    """
    specs = specs_from_text(
        'root ::= expr "+" term nl | expr nl\n'
        'expr ::= expr "+" term | term\nterm ::= [a-z]\nnl ::= "\\n"\n'
    )
    cont = specs.occurrence_follow("expr")
    assert cont.has("+") and cont.has("\n")
