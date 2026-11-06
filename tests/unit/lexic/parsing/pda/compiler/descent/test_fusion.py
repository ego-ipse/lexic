"""Tests for lexic.parsing.pda.compiler.descent.fusion — adjacent same-class items of a
text-only rule as one, in the grammar the predictive descent runs."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.compiler.descent.fusion import fused_grammar


def _rules(source: str) -> tuple[IrAst, dict[str, str]]:
    """``source``'s lifted grammar, and each rule of it fused, as text."""
    grammar = lift_optional_nullables(compile_text(source).codegen_grammar)
    fused = fused_grammar(grammar)
    return grammar, {str(rule.name): repr(rule.body) for rule in fused.rules}


def _body(source: str) -> str:
    """The body ``source``'s rule compiles to unfused, as text."""
    grammar = lift_optional_nullables(compile_text(source).codegen_grammar)
    return repr(grammar.rules[0].body)


@pytest.mark.parametrize(
    "spelling",
    ["[a-z]* [a-z]", "[a-z] [a-z]*", "[a-z]* [a-z]+", "[a-z]* [a-z] [a-z]?"],
)
def test_one_class_run_spelled_in_pieces_is_one_item(spelling: str) -> None:
    """Every spelling of one unbounded run of one class is the item ``[a-z]+`` is."""
    _grammar, fused = _rules(f"e ::= {spelling}\n")
    assert fused["e"] == _body("e ::= [a-z]+\n")


def test_bounded_runs_add_their_bounds() -> None:
    """``C{1,2} C{0,3}`` reads as ``C{1,5}``."""
    _grammar, fused = _rules("e ::= [a-z]{1,2} [a-z]{0,3}\n")
    assert fused["e"] == _body("e ::= [a-z]{1,5}\n")


def test_a_run_of_fixed_counts_alone_is_left_as_authored() -> None:
    """``C C``, as a hex escape's two digits, places no boundary by window:
    fusing it would save nothing, so it keeps its items."""
    grammar, fused = _rules("e ::= [0-9a-f] [0-9a-f] [0-9a-f]{2}\n")
    assert fused["e"] == repr(grammar.rules[0].body)


def test_a_looping_run_takes_its_fixed_neighbours() -> None:
    """``C C C*`` is one run of one class that loops: ``C{2,}`` as a whole."""
    _grammar, fused = _rules("e ::= [a-z] [a-z] [a-z]*\n")
    assert fused["e"] == _body("e ::= [a-z]{2,}\n")


def test_different_classes_and_other_items_stay_apart() -> None:
    """Only items of one class fuse: a subset class, a literal between two runs
    and a run of another class keep their places."""
    source = 'e ::= [a-z]* [aeiou] "-" [a-z]+ [0-9]+\n'
    grammar, fused = _rules(source)
    assert fused["e"] == repr(grammar.rules[0].body)


def test_a_rule_with_a_reference_is_left_as_authored() -> None:
    """A rule that references another builds a model of its parts, so where a
    run ends inside it is not invisible: it is not fused."""
    grammar, fused = _rules("e ::= [a-z]* [a-z] x\nx ::= [0-9]\n")
    assert fused["e"] == repr(grammar.rules[0].body)


def test_a_grammar_with_nothing_to_fuse_is_returned_itself() -> None:
    """No text-only rule spells a class run in pieces: the same grammar back."""
    grammar = lift_optional_nullables(
        compile_text('root ::= e ";"\ne ::= [a-z]+\n').codegen_grammar
    )
    assert fused_grammar(grammar) is grammar
