"""Tests for compile/reduction.py — the reducer-derived ``@lexical`` variant.

The derivation tiers are pinned on the native json grammar (whose reducer
exercises every tier) and on the GBNF self-grammar (whose pass-through bodies
pin the ``IrArg``-is-an-``int`` regression). The fold's end-to-end exactness
lives in the parity differential
(:mod:`tests.integration.lexic.parity.test_reduce_directives`).
"""

from __future__ import annotations

from lexic.compile.reduction import (
    ReduceDerivation,
    derive_reduction,
    sub_grammar,
)
from lexic.grammars import GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import (
    DROP,
    YIELD,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrMap,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
    IrTuple,
    Reducer,
)


def _json_derivation() -> ReduceDerivation:
    return derive_reduction(JSON_GRAMMAR, JSON_REDUCER)


def test_drop_refful_rules_are_marked():
    """DROP refful rules mark — their value is unused, the subtree collapses."""
    marks = _json_derivation().marks
    assert {"begin-object", "end-object", "begin-array", "end-array"} <= marks
    assert {"value-separator", "name-separator"} <= marks


def test_join_transparent_rule_is_marked():
    """A join-over-text-equivalent-children rule marks: its value IS the span."""
    # int = IrJoin(IrArgs()) over zero/digit1-9/digit, all text-equivalent.
    assert "int" in _json_derivation().marks


def test_channel_free_raise_bodies_are_marked():
    """IrRaise bodies mark — the refusal moves to fold time, same exception."""
    # frac/exp refuse via IrRaise — channel-free, so the refusal moves to
    # fold time with the same exception.
    assert {"frac", "exp"} <= _json_derivation().marks


def test_ref_free_rules_are_not_marked():
    """Ref-free rules derive no mark — already value_str, nothing changes."""
    # Already value_str — a mark changes nothing, so none is derived.
    derivation = _json_derivation()
    assert "digit" not in derivation.marks
    assert "unescaped" not in derivation.marks
    assert "true" not in derivation.marks


def test_recursive_structural_rules_are_not_marked():
    """Structural recursion never marks — inline_refs refuses the cycle."""
    derivation = _json_derivation()
    assert "value" not in derivation.marks
    assert "object" not in derivation.marks
    assert "member" not in derivation.marks


def test_conditional_run_hoists_char_with_derived_poison():
    """char* hoists to a marked run with the escape lead as derived poison."""
    derivation = _json_derivation()
    assert "char-run" in derivation.runs
    spec = derivation.runs["char-run"]
    assert spec.element == "char"
    # The escape arm's lead literal is the ONLY poison — derived, not named.
    assert spec.poison == frozenset({"\\"})
    assert "char-run" in derivation.marks


def test_run_rule_replaces_the_repetition_in_the_variant():
    """The variant's string rule references the run, not the repetition."""
    derivation = _json_derivation()
    string = next(r for r in derivation.variant.rules if str(r.name) == "string")
    atoms = [str(i.atom) for arm in string.body for i in arm]
    assert "char-run" in atoms
    assert "char" not in atoms


def test_dropped_non_semantic_rules_derive_construction_elision():
    """The shipped JSON reducer elides every declared structural-noise model."""
    derivation = _json_derivation()
    assert derivation.elide
    assert derivation.elide == JSON_GRAMMAR.non_semantic


def test_elision_requires_drop_and_never_elides_the_start_rule():
    """A flag alone is insufficient, and start has no parent noise policy."""
    grammar = IrAst(
        IrSeq(
            IrRule(
                "root",
                IrAlternation(IrSequence(IrItem(IrRuleRef("gap")))),
                False,
            ),
            IrRule(
                "gap",
                IrAlternation(IrSequence(IrItem(IrLiteral(" ")))),
                False,
            ),
        ),
        "root",
    )
    assert not derive_reduction(grammar, Reducer(default=YIELD)).elide
    dropped = Reducer(
        default=YIELD,
        noise=IrMap(
            IrTuple(IrRuleRef("root"), DROP),
            IrTuple(IrRuleRef("gap"), DROP),
        ),
    )
    assert derive_reduction(grammar, dropped).elide == frozenset({"gap"})


def test_pass_through_bodies_are_not_constants():
    """IrArg(0) IS an int — the constant tier must not swallow pass-throughs."""
    # IrArg(0) IS an int (a node is its payload); calling it a channel-free
    # constant collapsed every GBNF pass-through subtree to raw text.
    derivation = derive_reduction(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
    assert "quantifier" not in derivation.marks
    assert "lesc-short" not in derivation.marks


def test_sub_grammar_names_inner_groups():
    """Run sub-grammars name every inner group so no gtext collapse loses args."""
    ast, synthetic = sub_grammar(JSON_GRAMMAR, "char-run", "char")
    assert ast.start == "char-run"
    names = {str(r.name) for r in ast.rules}
    assert "char" in names and "hexdig" in names
    # char's escape group must be a named rule, or the model pipeline
    # collapses it to a gtext field and the hex args never exist as nodes.
    assert synthetic and synthetic <= names


def test_untouchable_grammar_derives_empty_marks():
    """A grammar the tiers cannot read derives the identity, not a refusal."""
    grammar = IrAst(
        IrSeq(
            IrRule(
                "word",
                IrAlternation(
                    IrSequence(IrItem(IrCharClass(IrRange(IrChr(97), IrChr(122)))))
                ),
            )
        ),
        "word",
    )
    derivation = derive_reduction(grammar, Reducer(default=YIELD))
    assert derivation.marks == frozenset()
    assert not derivation.runs
