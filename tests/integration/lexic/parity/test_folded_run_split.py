"""A left-recursive RUN — βs no separator leads — split and folded back exactly.

The folded source's first kind cuts at a separator a rule spells. A run has
none: ``item ::= item "a" | item "b" | "z"`` is a base and then bare steps. It
is cut before any character that begins a β, wherever the grammar proves no
piece holds one anywhere but first (`folded._run`), and a later piece re-wears
the base's own text to be a document again. Everything here asks one question
— is the stitched model the sequential one — at the policy's own cuts and at
cuts drawn at random among every offset the proof licenses.

Deep models are compared by :meth:`~lexic.model.GrammarModel.dump`: ``==``
recurses one C frame per level of a spine as deep as its document.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import CompiledGrammar, compile_text
from lexic.parsing.parallel.plan import folded
from lexic.parsing.parallel.plan.folded import folded_plan, locate, run_pieces
from lexic.parsing.parallel.stitch.interior import (
    fold_classes,
    fold_route,
    step_nodes,
    stitch_run,
)
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.extend.inner import rule_non_initials, seq_non_initial
from lexic.parsing.pda.compiler.leftrec.shape import foldable
from tests.split_helpers import engages
from tools.benchmark.cases.grammars import BENCHES

RUNS = {
    "start-fallback": ('root ::= root "a" | root "b" | "a"\n', "a", ("a", "b"), ""),
    "interior-exact": (
        'root ::= item nl\nitem ::= item "a" | item "b" | "a"\nnl ::= "\\n"\n',
        "a",
        ("a", "b"),
        "\n",
    ),
    "interior-climb": (
        'root ::= item tail\nitem ::= item "a" | item "b" | "z"\ntail ::= "zz\\n"\n',
        "z",
        ("a", "b"),
        "zz\n",
    ),
    "one arm, the start rule": ('root ::= root "a" | "a"\n', "a", ("a",), ""),
    "one arm, a start rule of its own": ('x ::= x "a" | "b"\n', "b", ("a",), ""),
    "two bare literals": (
        'root ::= x "!"\nx ::= x "a" | x "b" | "z"\n',
        "z",
        ("a", "b"),
        "!",
    ),
    "a capture beside a bare literal": (
        'root ::= x "!"\nx ::= x "a" | x op y | "z"\nop ::= "+"\ny ::= [b-d]\n',
        "z",
        ("a", "+b", "+c", "+d"),
        "!",
    ),
    "three arms, a base with a capture": (
        'root ::= x "!"\nx ::= x "a" | x "b" | x op y | w\nw ::= [w-z]+\n'
        'op ::= "+"\ny ::= [c-d]\n',
        "wxy",
        ("a", "b", "+c", "+d"),
        "!",
    ),
    "a literal past an arm's last capture": (
        'root ::= x "!"\nx ::= x "a" | x op y ";" | "z"\nop ::= "+"\ny ::= [b-d]\n',
        "z",
        ("a", "+b;", "+c;", "+d;"),
        "!",
    ),
    "an operator whose later characters a term spells": (
        'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]+\nop ::= "+a"\n',
        "xy",
        ("+abc", "+az", "+aq"),
        "",
    ),
    "a tail the spine can spell": (
        "root ::= expr sep\nexpr ::= expr op term | term\nterm ::= [a-z;]+\n"
        'op ::= "+"\nsep ::= ";"\n',
        "a;b",
        ("+c", "+d;e", "+;"),
        ";",
    ),
}
"""Every run-sound fold the suites and the roster hold: ``(grammar, base text,
step texts, the shell's tail)``. The first three are the bench rows' grammars;
the last two are spines the LED proof refuses (test_folded's sharp mark and
spelled tail), which the run kind takes because it removes no mark and reads
the extent off the shell's fixed width."""

ROWS = ("start-fallback", "interior-exact", "interior-climb")
WORKERS = (2, 8, 16)


def compiled(case: str) -> CompiledGrammar:
    """One case's artefact, compiled once."""
    return compile_text(RUNS[case][0], cache_key=f"folded-run-{case}")


def document(case: str, steps: int, seed: int) -> str:
    """The base, ``steps`` random β texts, then the tail."""
    _source, base, tokens, tail = RUNS[case]
    rng = random.Random(seed)
    return base + "".join(rng.choice(tokens) for _ in range(steps)) + tail


@pytest.mark.parametrize("case", RUNS)
def test_a_run_fold_has_a_run_plan_cut_at_its_step_characters(case: str) -> None:
    """No separator rule and no lead: the marks are the βs' first characters."""
    plan = folded_plan(compiled(case).codegen_grammar)
    assert plan is not None
    tokens = RUNS[case][2]
    assert plan.lead == "" and plan.steps
    assert set(plan.marks) == {token[0] for token in tokens}


@pytest.mark.parametrize("workers", WORKERS)
@pytest.mark.parametrize("case", RUNS)
def test_the_split_run_is_the_sequential_model(case: str, workers: int) -> None:
    """At the policy's own cuts, every worker count answers the sequential model."""
    artefact = compiled(case)
    text = document(case, 12_000, seed=workers)
    assert engages(artefact, text, cores=workers)
    sequential = artefact.parse(text, cores=1)
    parallel = artefact.parse(text, cores=workers)
    assert parallel.to_text() == text
    assert parallel.dump() == sequential.dump()


@pytest.mark.parametrize("workers", WORKERS)
@pytest.mark.parametrize("row", ROWS)
def test_the_bench_rows_split_their_own_sample(row: str, workers: int) -> None:
    """The rows engage on the very document the MT seats time."""
    bench = next(one for one in BENCHES if one.name == row)
    assert engages(bench.compiled, bench.full, cores=workers)
    sequential = bench.compiled.parse(bench.full, cores=1)
    assert bench.compiled.parse(bench.full, cores=workers).dump() == sequential.dump()


def stitched_run(artefact: CompiledGrammar, parts: tuple[str, ...]):
    """The run join over ``parts``, each parsed alone, as the split runs it."""
    plan = folded_plan(artefact.codegen_grammar)
    assert plan is not None
    route = fold_route(artefact.product, plan.chain)
    classes = fold_classes(artefact.product, plan)
    assert route is not None and classes is not None
    steps = step_nodes(classes)
    assert steps is not None
    stitched = stitch_run(
        [artefact.parse(part, cores=1) for part in parts], route, steps
    )
    assert stitched is not None
    return stitched


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("case", RUNS)
def test_any_licensed_cuts_fold_back_to_the_sequential_model(
    case: str, seed: int
) -> None:
    """Cuts drawn at random among every offset the plan licenses, below the
    policy's floor and side by side included: the soundness is the proof's,
    not the floor's, so it must hold wherever a mark stands."""
    artefact = compiled(case)
    plan = folded_plan(artefact.codegen_grammar)
    assert plan is not None
    text = document(case, 60, seed)
    region = locate(text, plan)
    assert region is not None
    first = min(
        at for at in range(region.opener + 1, region.closer) if text[at] in plan.marks
    )
    licensed = [at for at in range(first, region.closer) if text[at] in plan.marks]
    rng = random.Random(seed)
    cuts = sorted(rng.sample(licensed, rng.randint(1, min(6, len(licensed)))))
    stitched = stitched_run(artefact, run_pieces(text, region, plan, cuts).parts)
    assert stitched.dump() == artefact.parse(text, cores=1).dump()


# ── what the condition refuses, and why ───────────────────────────────────

UNSOUND = 'root ::= item\nitem ::= item "a" | "b" "a"\n'
"""test_fold_boundaries' "base closes on the step's character": the base's
second character begins a β, so a bare ``a`` past the spine's start may be the
base's own. A cut there would give the next piece one iteration too many."""

EMPTY_BASE = 'root ::= x "!"\nx ::= x "a" | "b"?\n'
"""A base that can be empty leaves the spine's first β at its start, so the
text before the first mark is not the base and cannot be re-worn as one."""


def _taken(source: str, key: str):
    """The fold the grammar's rule takes, its grammar, and its analysis."""
    grammar = compile_text(source, cache_key=key).codegen_grammar
    rules = {str(rule.name): rule for rule in grammar.rules}
    analysis = GrammarAnalysis(grammar)
    fold = next(
        (name, found)
        for name, rule in rules.items()
        if (found := foldable(name, rule, rules, analysis)) is not None
    )
    return fold, grammar, rules, analysis


def test_a_base_holding_a_step_character_past_its_first_is_refused() -> None:
    """The fold takes the rule, and the run plan refuses it for exactly the
    NON_INITIAL overlap: the base derives ``a`` past its first character."""
    (name, fold), grammar, rules, analysis = _taken(UNSOUND, "folded-run-unsound")
    starts = analysis.seq_first(list(fold.steps[0].rest))
    base = list(tuple(rules[name].body)[fold.base[0]])
    assert seq_non_initial(base, rule_non_initials(rules)).overlaps(starts)
    assert folded_plan(grammar) is None


def test_an_empty_base_is_refused() -> None:
    """The fold takes ``x``, and the run plan refuses its nullable base."""
    (name, fold), grammar, rules, analysis = _taken(EMPTY_BASE, "folded-run-empty")
    base = list(tuple(rules[name].body)[fold.base[0]])
    assert all(analysis.item_nullable(one) for one in base)
    assert folded_plan(grammar) is None


def test_the_condition_is_read_once_per_grammar(monkeypatch) -> None:
    """NON_INITIAL is a plan-time fact: three documents, one fixpoint."""
    calls = []
    real = folded.rule_non_initials
    monkeypatch.setattr(
        folded, "rule_non_initials", lambda rules: calls.append(1) or real(rules)
    )
    artefact = compile_text(RUNS["two bare literals"][0], cache_key="folded-run-once")
    for seed in range(3):
        text = document("two bare literals", 12_000, seed)
        assert engages(artefact, text, cores=4)
    assert len(calls) == 1
