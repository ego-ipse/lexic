"""Tests for lexic.parsing.pda.compiler.leftrec.rewrite — the grammar the PDA runs.

Three things the rewrite must get right, each with its own way of being subtly
wrong: the SHAPE it produces (one arm, base then unbounded step), the ORPHANS
it drops, and the fact that it touches the PDA's grammar and not the shared one.

The orphan case is not housekeeping and has its own test because it was a real
defect: `hoist_arms` leaves the old arm rule referenced by nothing, the FOLLOW
fixpoint walks every rule regardless, and that corpse puts the operator's FIRST
straight back into FOLLOW of the folded rule — so the new loop reads as "overlap,
not gatable" and the rule islands again for a reason no longer in the language.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrItem, IrRuleRef
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.leftrec.rewrite import fold_grammar
from lexic.parsing.pda.compiler.leftrec.shape import foldable

_SOURCE = (
    'root ::= expr "!"\nexpr ::= expr op term | term\nterm ::= [a-z]\nop ::= "+"\n'
)


def rewritten_grammar(source: str = _SOURCE):
    """``source`` lifted, and lifted-then-folded, for comparison."""
    compiled = compile_text(source, cache_key=f"rw-{hash(source)}")
    grammar = lift_optional_nullables(compiled.codegen_grammar)
    analysis = GrammarAnalysis(grammar)
    rules = {str(one.name): one for one in grammar.rules}
    shapes = {
        name: got
        for name, rule in rules.items()
        if (got := foldable(name, rule, rules, analysis.item_nullable)) is not None
    }
    return grammar, fold_grammar(grammar, shapes)


def rule_named(grammar, name: str):
    """One rule of ``grammar`` by name."""
    return next(one for one in grammar.rules if str(one.name) == name)


def test_the_rewritten_rule_is_one_arm_of_base_then_unbounded_step() -> None:
    """``A ::= A β | γ`` becomes ``A ::= (γ) (β)*`` — one arm, two items.

    The step must be UNBOUNDED: a bounded one would accept a shorter language
    than the recursion did, which is the one thing the classical rewrite is
    supposed to guarantee it does not do.
    """
    _before, after = rewritten_grammar()
    body = rule_named(after, "expr").body

    assert len(body) == 1, "one arm"
    items = [one for one in body[0] if isinstance(one, IrItem)]
    assert len(items) == 2, "the base, then the step"
    assert int(items[0].quantifier.lo) == 1
    assert items[0].quantifier.hi == 1, "the base is taken exactly once"
    assert int(items[1].quantifier.lo) == 0
    assert not isinstance(items[1].quantifier.hi, int), "the step repeats without bound"


def test_the_orphaned_arm_rule_is_dropped() -> None:
    """``expr-arm1`` is referenced by nothing after the fold, and must go.

    Leaving it is not harmless: the FOLLOW fixpoint walks every rule in the
    grammar, so the dead arm feeds ``op``'s FIRST back into FOLLOW(``expr``)
    and the new loop is refused as ungatable.
    """
    before, after = rewritten_grammar()

    assert any(str(one.name) == "expr-arm1" for one in before.rules)
    assert not any(str(one.name) == "expr-arm1" for one in after.rules)


def test_the_folded_rule_no_longer_islands() -> None:
    """The point of the whole exercise, asserted on the analysis itself."""
    _before, after = rewritten_grammar()

    assert "expr" not in GrammarAnalysis(after).islands


def test_nothing_reachable_is_dropped_with_the_orphans() -> None:
    """Dropping unreachable rules must not drop a rule something still uses.

    The orphan sweep is reachability from the start rule, so a bug in it would
    silently delete live rules and the grammar would refuse its own language.
    """
    _before, after = rewritten_grammar()
    names = {str(one.name) for one in after.rules}

    for rule in after.rules:
        for node in rule.body:
            for item in (one for one in node if isinstance(one, IrItem)):
                if isinstance(item.atom, IrRuleRef):
                    assert str(item.atom) in names, (
                        f"{item.atom} was dropped but is used"
                    )


def test_a_grammar_with_nothing_to_fold_is_returned_unchanged() -> None:
    """No folds means the same object back — the rewrite does not churn."""
    compiled = compile_text('root ::= "a" | "b"\n', cache_key="rw-nofold")
    grammar = lift_optional_nullables(compiled.codegen_grammar)

    assert fold_grammar(grammar, {}) is grammar
