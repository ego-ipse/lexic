"""Tests for lexic.parsing.pda.compiler.descent — the grammar the descent runs."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.compiler.descent import descent_grammar
from lexic.parsing.products import model_product


def _descent(source: str):
    """``source``'s descent grammar and folds, from its lifted grammar."""
    compiled = compile_text(source)
    product = model_product(compiled.codegen_grammar, compiled.product)
    lifted = lift_optional_nullables(compiled.codegen_grammar)
    return lifted, descent_grammar(lifted, product.binding)


def test_both_rewrites_apply_in_one_grammar() -> None:
    """A left-recursive rule folds and a text-only run fuses, in one pass: the
    fold's build comes back for the folded rule, and the run is one item."""
    lifted, (grammar, folds) = _descent(
        'root ::= expr "!" word\nexpr ::= expr op term | term\nterm ::= [a-z]\n'
        'op ::= "+"\nword ::= [a-z]* [a-z]\n'
    )
    assert "expr" in folds
    rules = {str(rule.name): rule for rule in grammar.rules}
    assert len(rules["word"].body[0]) == 1
    assert len({str(rule.name): rule for rule in lifted.rules}["word"].body[0]) == 2


def test_a_grammar_neither_rewrite_takes_is_returned_itself() -> None:
    """Nothing folds and nothing fuses: the lifted grammar itself, no folds."""
    lifted, (grammar, folds) = _descent('root ::= e ";"\ne ::= [a-z]+\n')
    assert grammar is lifted
    assert not folds
