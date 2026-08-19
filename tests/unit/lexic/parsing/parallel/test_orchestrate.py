"""Tests for ``lexic.parsing.parallel.orchestrate`` — the split parse.

The contract is equality, not speed: a split parse produces the model the
sequential parse produces, or it IS the sequential parse. Every shape the
stitch does not support, and every failing chunk, falls back — so what an
input MEANS never depends on how many workers ran.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model, split_plan

LEAD_RULE = (
    "root ::= pair tail*\n"
    "tail ::= comma pair\n"
    'comma ::= "," ws\n'
    'pair ::= [a-z]+ ":" [0-9]+\n'
    'ws ::= " "*\n'
)
BARE_LEAD = 'root ::= word more*\nmore ::= "|" word\nword ::= [a-z]+\n'
NO_SPLIT = 'root ::= "a" [b-z]+\n'


def _doc(count: int = 40) -> str:
    return ", ".join(f"key{'x' * (i % 7)}:{i}" for i in range(count))


def test_split_equals_sequential_and_round_trips():
    """The headline: same model, exactly, and the text comes back."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = _doc()
    parallel = split_model(grammar, text, fold, cores=4)
    assert parallel is not None
    assert parallel == parse_model(grammar, text, fold)
    assert parallel.to_text() == text
    assert compiled.parse(text) == parallel


@pytest.mark.parametrize("cores", [2, 3, 5, 8])
def test_every_worker_count_gives_one_answer(cores: int):
    """Worker count moves wall-clock, never the value."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = _doc()
    assert split_model(grammar, text, fold, cores=cores) == parse_model(
        grammar, text, fold
    )


def test_a_bare_literal_lead_splits_too():
    """``more ::= "|" word`` has no lead RULE — the cut text is the literal."""
    compiled = compile_text(BARE_LEAD)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = "|".join(f"word{'x' * (i % 3)}" for i in range(30)).replace("0", "")
    assert split_model(grammar, text, fold, cores=4) == parse_model(grammar, text, fold)


def test_a_grammar_without_a_separated_start_has_no_plan():
    """No plan is an answer: ``None`` tells the caller to parse sequentially."""
    compiled = compile_text(NO_SPLIT)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    assert split_plan(grammar) is None
    assert split_model(grammar, "abc", fold, cores=4) is None


def test_a_bad_input_declines_rather_than_inventing_a_refusal():
    """A failing chunk is a verdict on the SPLIT, not on the input: the
    split declines and the caller's sequential parse is what raises."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    bad = _doc() + ", 12:not-a-pair"
    assert split_plan(grammar) is not None, "the decline must not be 'no plan'"
    assert split_model(grammar, bad, fold, cores=4) is None
    with pytest.raises(UnsupportedConstructError):
        compiled.parse(bad)


def test_too_few_separators_declines():
    """No cut points, no split — and the artefact still parses it."""
    compiled = compile_text(LEAD_RULE)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    text = "only:1"
    assert split_model(grammar, text, fold, cores=8) is None
    assert compiled.parse(text).to_text() == text


def test_plan_is_memoised_per_grammar():
    """The shape analysis runs once per grammar identity."""
    compiled = compile_text(LEAD_RULE)
    grammar = compiled.codegen_grammar
    assert split_plan(grammar) is split_plan(grammar)
