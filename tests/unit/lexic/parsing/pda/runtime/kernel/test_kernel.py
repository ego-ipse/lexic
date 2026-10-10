"""Tests for pda.runtime.kernel.kernel — the fused-runtime parity gate (Task 4).

:func:`~lexic.parsing.pda.runtime.kernel.kernel.pda_model` builds a
model directly during the walk (fold fusion, no
:class:`~lexic.parsing.earley.kernel.forest.forest.ParseTree`). The
bar here is ``semantic_dump()`` equality + ``to_text()`` round-trip against
the engine's own ``fold.apply(parse_first(...))`` path; the raw-equality
invariant — both engines build the SAME model, field for field (ruled
2026-07-28) — is owned by the integration raw-parity test, which covers
these grammars too.

Scoped to the four **island-free** ground-truth grammars (arithmetic.gbnf,
japanese.gbnf, list.gbnf, arithmetic.abnf — see the pinned island sets in
``test_analysis.py`` / ``test_clones.py``, all empty for these four): Task
4 leaves island references raising :exc:`~lexic.parsing.pda.runtime.kernel.kernel.PdaFail`
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
from lexic.compile.pipeline.moments import build_codegen_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.grammars import GBNF_FLAVOUR
from lexic.model import GrammarModel
from lexic.parsing import ParseConfig
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_pda
from lexic.parsing.pda.compiler.program.flatten import FlatClone, clone_arms
from lexic.parsing.pda.compiler.program.opcodes import OP_LIT1, OP_V1, OP_VDISP, OP_VRUN
from lexic.parsing.pda.runtime import matchers as matchers_module
from lexic.parsing.pda.runtime.islands import IslandPolicy
from lexic.parsing.pda.runtime.kernel import execution as execution_module
from lexic.parsing.pda.runtime.kernel import kernel as kernel_module
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail, PdaKernel, pda_model
from lexic.parsing.products import earley_model, model_product
from tests.clone_walk import walk_program_clones
from tests.integration.lexic.parity.pda_parity_helpers import (
    arithmetic_bench_corpus,
    deep_semantic,
    forced_engine,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import (
    assert_parity,
    compiled_and_pda,
    path_specs,
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
    the engine-fallback path — not a parity failure); any *other* grammar's
    :exc:`PdaFail` is a genuine, unexpected divergence and fails the test
    outright (these four are island-free — nothing should force a fallback).
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


def test_interning_shares_every_equal_value_str_submodel() -> None:
    """Interning covers the ``value_str`` builds — equal ones ARE one instance.

    Records are deliberately NOT interned: their key needed a second projection
    of every field (strings by value, sub-models by ``id``) that cost more than
    the tuple construction a hit saves, and it hit as rarely as 0% on the csv
    corpus. What the parity gate promises is value equality with the engine
    reference (the test above), never record identity. ``value_str`` keeps its
    memo because ``(ctor, span)`` is already at hand.
    """
    path = GROUND_TRUTH / "arithmetic.gbnf"
    compiled, pda = compiled_and_pda(path)
    text = _INTERN_CORPUS["arithmetic.gbnf"]
    built = pda_model(pda, text, compiled.executor)
    kinds = {b.rule_name: b.kind for b in compiled.moments.binding}
    classes = {
        name: kinds.get(str(getattr(cls, "__grammar__").name))
        for name, cls in compiled.classes.items()
    }
    shared: dict[tuple[type, GrammarModel], int] = {}
    for model in _all_models(built):
        if classes.get(type(model).__name__) != "value_str":
            continue
        first = shared.setdefault((type(model), model), id(model))
        assert id(model) == first, (
            f"equal value_str models not shared — {type(model).__name__} {model!r}"
        )
    assert shared, "corpus produced no value_str sub-models to share"


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
    pda = compile_pda(lifted, normalize(lifted), compiled.product)
    for inp in ("ab", "cab"):
        with pytest.raises(PdaFail):
            pda_model(pda, inp, compiled.executor)


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

    config = ParseConfig(resolve=take_first)
    kern = PdaKernel(pda, "{}", compiled.executor, config=config)
    assert isinstance(kern.policy, IslandPolicy)
    assert kern.policy.executor is compiled.executor
    assert kern.policy.config is config
    assert kern.policy.delegates is None  # filled per island, at the reference


# ── an exactly-once tabled reference inside a frame ────────────────────

FRAMED_ONCE = (
    'root ::= ws sign body\nws ::= [ ]*\nsign ::= "+" | "-"\n'
    'body ::= "<" kw ">"\nkw ::= "ab"\n'
)
"""``root`` keeps a frame — ``body`` is still a descent when leaves are marked —
and both of its value references are exactly once, to TABLED clones: ``ws`` a
run the span table answers (``OP_VRUN``), ``sign`` a one-character language
the char table answers (``OP_V1``)."""


def test_a_framed_exactly_once_reference_calls_its_matcher_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OP_VRUN`` and ``OP_V1`` have no loop to run, in a frame as in a leaf.

    Both targets carry a table, so through the loop driver each went into
    ``match_chartable`` for one iteration; the pin is that the framed walk never
    enters it for either code, and that the model is still the Earley engine's.
    """
    compiled = compile_text(FRAMED_ONCE, flavour="gbnf", cache_key="framed-once")
    product = model_product(compiled.codegen_grammar, compiled.product)
    root = next(
        clone
        for clone in walk_program_clones(product.pda.program.start).values()
        if clone.name == "root"
    )
    assert not root.leaf, "root must keep a frame for this pin to mean anything"
    targets = {
        kind: arm.payloads[i]
        for arm in clone_arms(root)
        for i, kind in enumerate(arm.kinds)
        if kind in (OP_VRUN, OP_V1)
    }
    assert set(targets) == {OP_VRUN, OP_V1}, "the grammar no longer reaches both codes"
    assert targets[OP_VRUN].runarm is not None
    assert targets[OP_V1].runarm is None and targets[OP_V1].chartable is not None
    expected = {
        text: earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
        for text in ("  +<ab>", "-<ab>")
    }

    def no_loop(*_args: object) -> int:
        raise AssertionError("an exactly-once reference ran the table loop")

    runs: list[FlatClone] = []
    real_run = execution_module.run_span_once

    def counted_run(text: str, clone: FlatClone, sink: list, pos: int) -> int:
        runs.append(clone)
        return real_run(text, clone, sink, pos)

    monkeypatch.setattr(execution_module, "match_chartable", no_loop)
    monkeypatch.setattr(execution_module, "run_span_once", counted_run)
    for text, model in expected.items():
        runs.clear()
        assert pda_model(product.pda, text, compiled.executor) == model
        assert model.to_text() == text
        # the run's own matcher, called straight from the frame: not answered
        # on a detour through `vstr_once` (a leaf may call it for its own items)
        assert targets[OP_VRUN] in runs
    with pytest.raises(PdaFail):  # the table's refusal, through the direct call
        pda_model(product.pda, " *<ab>", compiled.executor)


# ── an entry the selector walk cannot decide ───────────────────────────

ENTERED = 'root ::= "<" pair ">"\npair ::= w w\nw ::= [a-z]+ " "?\n'
"""``root``: one arm, opening on a literal, keeping a frame."""


def test_an_entry_with_one_self_refusing_arm_skips_the_walk() -> None:
    """With the walk's own selectors emptied, the entry still finds the arm —
    it never walked them — and the literal still refuses what the walk did."""
    compiled = compile_text(ENTERED, flavour="gbnf", cache_key="entry-straight")
    product = model_product(compiled.codegen_grammar, compiled.product)
    root = next(
        clone
        for clone in walk_program_clones(product.pda.program.start).values()
        if clone.name == "root"
    )
    assert root.entry is not None
    text = "<ab cd>"
    expected = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    root.selectors = ()  # the walk would now refuse every entry
    assert pda_model(product.pda, text, compiled.executor) == expected
    with pytest.raises(PdaFail):
        pda_model(product.pda, "(ab cd>", compiled.executor)


DEFAULTED = 'root ::= opt "z"\nopt ::= "a" x | ""\nx ::= "(" root ")" | "p"\n'
"""``opt``: one selector arm opening on a literal, and an empty default."""


def test_a_walk_with_a_default_to_take_keeps_its_selectors() -> None:
    """The walk is not undecided when a default answers what the selector
    refuses: no entry, and a lookahead the default takes parses on the PDA —
    an entry would push the literal's arm there and refuse."""
    compiled = compile_text(DEFAULTED, flavour="gbnf", cache_key="entry-default")
    product = model_product(compiled.codegen_grammar, compiled.product)
    opt = next(
        clone
        for clone in walk_program_clones(product.pda.program.start).values()
        if clone.name == "opt"
    )
    assert opt.default is not None and len(opt.selectors) == 1
    assert opt.selectors[0][2].kinds[0] == OP_LIT1
    assert opt.entry is None
    for text in ("z", "apz"):
        expected = earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
        assert pda_model(product.pda, text, compiled.executor) == expected


# ── an entered span-tabled leaf ────────────────────────────────────────

ENTERED_RUNS = (
    "# @lexical event span\n"
    'root ::= record+\nrecord ::= event | span | group\ngroup ::= "(" record+ ")"\n'
    'event ::= "%" [a-z]+ ("," [a-z]+)* ";"\nspan ::= "<" [0-9]+ ">"\n'
)
"""``record`` is a dispatch over two proved, span-tabled leaves and a framed
``group``, looped by ``root``: the framed target keeps the loop from being
matched inline, so each occurrence is ENTERED, through the chase."""


def test_an_entered_span_tabled_leaf_goes_straight_to_its_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The entry runs the leaf's span table, not ``vstr_once``'s selection
    first; the model is still the Earley engine's."""
    compiled = compile_text(ENTERED_RUNS, flavour="gbnf", cache_key="entered-runs")
    product = model_product(compiled.codegen_grammar, compiled.product)
    leaves = [
        clone
        for clone in walk_program_clones(product.pda.program.start).values()
        if clone.leaf and clone.runarm is not None and clone.name in ("event", "span")
    ]
    assert {clone.name for clone in leaves} == {"event", "span"}
    text = "%ab,cd;<12>(%c;)<3>"
    expected = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    runs: list[FlatClone] = []
    real_run = execution_module.run_span_once

    def counted_run(text: str, clone: FlatClone, sink: list, pos: int) -> int:
        runs.append(clone)
        return real_run(text, clone, sink, pos)

    def no_selection(*_args: object) -> int:
        raise AssertionError("an entered span-tabled leaf went through vstr_once")

    monkeypatch.setattr(execution_module, "run_span_once", counted_run)
    monkeypatch.setattr(execution_module, "vstr_once", no_selection)
    assert pda_model(product.pda, text, compiled.executor) == expected
    assert len(runs) == 4


# ── a loop over a dispatch of span-tabled clones, matched inline ──────

INLINE_RUNS = (
    "# @lexical event span\n"
    'root ::= record+ "!"\nrecord ::= event | span\n'
    'event ::= "%" [a-z]+ ("," [a-z]+)* ";"\nspan ::= "<" [0-9]+ ">"\n'
)
"""``record`` dispatches to two span-tabled clones only, so ``root``'s loop
over it is an ``OP_VDISP`` item: chased and run per occurrence, no entry."""


def test_a_loop_over_span_tabled_landings_runs_inline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each occurrence is the chase and the landed clone's run: never the
    selection of ``vstr_once``, never a call to ask the stop gate, and the
    model is still the Earley engine's."""
    compiled = compile_text(INLINE_RUNS, flavour="gbnf", cache_key="inline-runs")
    product = model_product(compiled.codegen_grammar, compiled.product)
    root = next(
        clone
        for clone in walk_program_clones(product.pda.program.start).values()
        if clone.name == "root"
    )
    assert OP_VDISP in {kind for arm in clone_arms(root) for kind in arm.kinds}
    text = "%ab,cd;<12>%c;<3>!"
    expected = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )

    def refused(*_args: object) -> int:
        raise AssertionError("an inline span-tabled landing took a detour")

    monkeypatch.setattr(matchers_module, "vstr_once", refused)
    monkeypatch.setattr(execution_module, "gate_take", refused)
    assert pda_model(product.pda, text, compiled.executor) == expected


LEAF_ENTERED = 'root ::= "<" pair+ ">"\npair ::= "a" w ";"\nw ::= [b-z]+\n'
"""``pair``: a leaf, entered per iteration of ``root``'s loop, one arm opening
on a literal."""


def test_a_leaf_with_one_self_refusing_arm_runs_it_without_the_walk() -> None:
    """With its own selectors emptied the leaf run still finds its arm — it
    never walked them — the literal still refuses what the walk did, and the
    model is the Earley engine's."""
    compiled = compile_text(LEAF_ENTERED, flavour="gbnf", cache_key="leaf-entry")
    product = model_product(compiled.codegen_grammar, compiled.product)
    pair = next(
        clone
        for clone in walk_program_clones(product.pda.program.start).values()
        if clone.name == "pair"
    )
    assert pair.leaf and pair.entry is not None
    text = "<abc;ad;>"
    expected = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    pair.selectors = ()  # the walk would now refuse every run
    assert pda_model(product.pda, text, compiled.executor) == expected
    with pytest.raises(PdaFail):
        pda_model(product.pda, "<abc;b;>", compiled.executor)


# ── a descent loop asks its wide gate straight ─────────────────────────


def test_a_descent_loop_asks_its_wide_gate_without_the_dispatching_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_quant_step`` settles the stop and attempt kinds itself, so a wide
    gate (json.gbnf's post-noise peeks) is asked through ``wide_gate_take``
    straight, never through ``gate_take``'s kind dispatch; the model is still
    the Earley engine's."""
    compiled, _pda = compiled_and_pda(GROUND_TRUTH / "json.gbnf")
    product = model_product(compiled.codegen_grammar, compiled.product)
    text = '{"a": [1, 2, {"b": "c"}], "d": {}}'
    expected = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    asked: list[int] = []
    real_wide = kernel_module.wide_gate_take

    def counted_wide(text: str, pos: int, gk: int, gate: object) -> bool:
        asked.append(gk)
        return real_wide(text, pos, gk, gate)

    monkeypatch.setattr(kernel_module, "wide_gate_take", counted_wide)
    assert pda_model(product.pda, text, compiled.executor) == expected
    assert asked, "no wide gate was asked: the pin would pass vacuously"
