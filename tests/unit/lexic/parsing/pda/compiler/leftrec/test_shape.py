"""Tests for lexic.parsing.pda.compiler.leftrec.shape — what the fold may take.

The shape reader decides which rules get rewritten, so every wrong answer here
is a wrong model somewhere else: a shape it takes that it should not is a rule
parsed as a loop and built through a routine that does not fit it, and a shape
it declines is a rule that keeps islanding for no reason.

Each refusal has its own case because each is a different way to be wrong, and
the reading-through-the-hoist case is first because without it the reader
matches NOTHING — `hoist_arms` lifts every arm into its own rule before the PDA
sees the grammar, so direct left recursion is indirect by construction and a
test for the direct shape finds zero rules across the whole corpus.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAst, IrRule, IrRuleRef
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.leftrec import shape as shape_module
from lexic.parsing.pda.compiler.leftrec.shape import Fold, any_candidate, foldable
from lexic.parsing.pda.compiler.specs import arm_items
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES


def shapes(source: str) -> dict[str, Fold]:
    """Every rule of ``source`` the fold would take, by name."""
    compiled = compile_text(source, cache_key=f"shape-{hash(source)}")
    grammar = lift_optional_nullables(compiled.codegen_grammar)
    analysis = GrammarAnalysis(grammar)
    rules: dict[str, IrRule] = {str(one.name): one for one in grammar.rules}
    return {
        name: got
        for name, rule in rules.items()
        if (got := foldable(name, rule, rules, analysis)) is not None
    }


def test_the_shape_is_read_through_the_hoisted_arm_rule() -> None:
    """``expr ::= expr op term | term`` folds, though it never arrives that way.

    `hoist_arms` turns it into ``expr ::= expr-arm1 | term`` with
    ``expr-arm1 ::= expr op term``, so the direct shape is not present in the
    grammar the fold reads. Undoing that hoist is what makes the reader match
    anything at all.
    """
    got = shapes(
        'root ::= expr "!"\nexpr ::= expr op term | term\nterm ::= [a-z]\nop ::= "+"\n'
    )

    assert "expr" in got
    fold = got["expr"]
    assert len(fold.steps) == 1
    assert fold.steps[0].rule == "expr-arm1", "the step names the ARM's rule"
    assert fold.base, "and the base arm is kept"


def test_the_step_carries_the_arm_rule_whose_routine_builds_the_node() -> None:
    """The fold calls a routine, so it has to name which one.

    The nested node is built by the hoisted arm's routine, not by the rule's —
    the rule itself is an alternation that builds nothing. A step that did not
    carry that name would have no way to build its iteration.
    """
    fold = shapes('root ::= x "!"\nx ::= x "d" | "a"\n')["x"]

    assert fold.steps[0].rule.startswith("x-arm")
    assert fold.steps[0].rest, "and the β it repeats"


def test_indirect_recursion_is_refused() -> None:
    """``x`` reaching itself through ``y`` is not the shape and is left alone.

    The rewrite is only language-preserving for the direct form. Taking this
    would rewrite a rule whose recursion it has not actually removed.
    """
    assert "x" not in shapes('root ::= x "e"\nx ::= y "a" | "b"\ny ::= x\n')


def test_a_vanishing_beta_is_refused() -> None:
    """A β that can spell nothing would make ``(β)*`` an infinite loop.

    The rewritten rule would accept the same language and never terminate on
    it, which is worse than islanding.
    """
    assert "x" not in shapes('root ::= x "e"\nx ::= x opt | "b"\nopt ::= "d"?\n')


def test_a_rule_with_no_base_arm_is_refused() -> None:
    """Every arm recursing means the rule derives no finite string.

    There is nothing for the fold to start from, and `(γ)` would be empty.
    """
    assert "x" not in shapes('root ::= x "e"\nx ::= x "d" | x "c"\n')


def test_a_rule_that_does_not_recurse_is_not_a_fold() -> None:
    """The ordinary case: nothing to do, and the reader says so by declining."""
    got = shapes('root ::= x "e"\nx ::= "a" | "b"\n')

    assert "x" not in got
    assert not got, "no rule in this grammar folds"


def test_the_pre_test_agrees_with_the_full_test_wherever_it_matters() -> None:
    """`any_candidate` may say yes wrongly; it must never say NO wrongly.

    It exists to skip building a `GrammarAnalysis` on a grammar that cannot
    fold, which is nearly every grammar — so the skip is the common path and
    the analysis the rare one. A pre-test that could answer NO for a grammar
    that DOES fold would silently stop folding it, and nothing downstream
    would notice because not folding is a legal outcome.

    So the direction is checked, not just the agreement: every grammar the
    full test finds a fold in must pass the pre-test.
    """
    for bench in BENCHES:
        grammar = lift_optional_nullables(bench.compiled.codegen_grammar)
        analysis = GrammarAnalysis(grammar)
        rules = {str(one.name): one for one in grammar.rules}
        folds = any(
            foldable(name, rule, rules, analysis) is not None
            for name, rule in rules.items()
        )
        if folds:
            assert any_candidate(rules), f"{bench.name}: folds but the pre-test said no"


def test_the_pre_test_skips_a_grammar_with_nothing_self_leading() -> None:
    """The common case, and the one the saving is for."""
    compiled = compile_text('root ::= a "!"\na ::= "x" | "y"\n', cache_key="pre-none")
    grammar = lift_optional_nullables(compiled.codegen_grammar)

    assert not any_candidate({str(one.name): one for one in grammar.rules})


def _corpus() -> list[tuple[str, IrAst]]:
    """Every grammar the project ships, as codegen grammars the PDA sees."""
    rows = [(bench.name, bench.compiled.codegen_grammar) for bench in BENCHES]
    for path in sorted(GROUND_TRUTH.glob("*.[gae]*")):
        if path.suffix in {".gbnf", ".abnf", ".ebnf"}:
            rows.append((path.name, compile_from_path(path).codegen_grammar))
    return rows


def _direct_left_recursive(rules: dict[str, IrRule]) -> list[str]:
    """Rules with an arm whose FIRST item references the rule itself.

    The textbook shape, spelled out here rather than imported: a census that
    asked the reader under test what the shape is would agree with it by
    construction and prove nothing.
    """
    return [
        name
        for name, rule in rules.items()
        for arm in rule.body
        if (items := arm_items(arm))
        and isinstance(items[0].atom, IrRuleRef)
        and str(items[0].atom) == name
    ]


def test_nothing_in_the_corpus_is_directly_left_recursive() -> None:
    """Why the reader reads through a hoisted arm instead of matching `A ::= A β`.

    `hoist_arms` lifts every arm into its own rule before the PDA sees the
    grammar, so direct left recursion is indirect by construction: the
    recursion arrives one rule below where it was written. A reader matching
    only the direct shape would find nothing to fold in anything shipped.

    Two guards keep the census from being vacuous. A blind detector would
    report zero, so it is first shown to fire on the same grammar BEFORE the
    hoist; and a corpus with no left recursion at all would report zero, so
    the fold must find something to take through the hoist.
    """
    written = parse_grammar('x ::= x "d" | "a"\n', GBNF_FLAVOUR)
    assert _direct_left_recursive({str(one.name): one for one in written.rules}) == [
        "x"
    ], "the detector does not match the shape it exists to find"

    direct: list[str] = []
    folding: list[str] = []
    for label, codegen in _corpus():
        grammar = lift_optional_nullables(codegen)
        rules = {str(one.name): one for one in grammar.rules}
        analysis = GrammarAnalysis(grammar)
        direct += [f"{label}:{name}" for name in _direct_left_recursive(rules)]
        folding += [
            f"{label}:{name}"
            for name, rule in rules.items()
            if foldable(name, rule, rules, analysis) is not None
        ]

    assert not direct, f"the direct shape the reader does NOT match: {direct}"
    assert folding, "nothing folds anywhere — the zero above proves nothing"


# ── the boundary proof — every carving of a fold's pieces is the text's ─────

UNSETTLED = {
    "width-0 base run": 'root ::= item\nitem ::= item "a" | x\nx ::= "b" "a"*\n',
    "width-1 base run": 'root ::= item\nitem ::= item y | x\ny ::= "a"\nx ::= "b" "a"*\n',
    "base arm prefix": 'root ::= item\nitem ::= item "a" | x\nx ::= "b" | "ba"\n',
    "step into step": 'root ::= item\nitem ::= item x | "c"\nx ::= "a"+\n',
    "word holds the operator": (
        'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]+\nop ::= "and"\n'
    ),
}
"""Shapes the fold would take whose pieces can be carved two ways. Each is
genuinely ambiguous — ``ba`` is ``x("ba")`` or ``x("b")`` then ``"a"``,
``caa`` is one ``x`` or two, ``aandb`` one word or ``a and b``."""

SETTLED = {
    "base closes on the step's character": 'root ::= item\nitem ::= item "a" | "b" "a"\n',
    "run then an operator it cannot hold": (
        'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]+\nop ::= "+"\n'
    ),
    "step whose run cannot start a step": 'root ::= item\nitem ::= item x | "c"\nx ::= "a" "b"*\n',
}
"""The near misses: the same characters in play, and no piece can be lengthened
into where a β begins."""


@pytest.mark.parametrize("case", sorted(UNSETTLED))
def test_a_fold_whose_pieces_can_be_carved_two_ways_is_refused(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shape qualifies and the boundary proof refuses it, whatever the width."""
    source = UNSETTLED[case]
    assert not shapes(source), f"{case}: folded, so the descent would pick one"
    monkeypatch.setattr(shape_module, "settled", lambda *_args: True)
    assert shapes(source), (
        f"{case}: the SHAPE stopped qualifying, so this proves nothing"
    )


@pytest.mark.parametrize("case", sorted(SETTLED))
def test_a_fold_whose_boundaries_the_text_fixes_still_folds(case: str) -> None:
    """The near misses keep the fold."""
    assert shapes(SETTLED[case]), f"{case}: refused, and would island for nothing"
