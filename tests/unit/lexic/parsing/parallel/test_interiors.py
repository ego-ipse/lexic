"""Tests for ``lexic.parsing.parallel.interiors`` — the opaque regions.

A comma inside a string is TEXT, not a separator. The delimited region that
makes it so is DERIVED from the grammar's own shape — a rule whose one arm
opens and closes with the same single-character literal around a repeated
body — so every json formulation yields the same answer without any of them
being named.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel.interiors import Interior, interiors
from tests.paths import GROUND_TRUTH

JSON_FORMULATIONS = ("json.gbnf", "json.abnf", "json.ebnf")


def _interiors(source: str) -> tuple[Interior, ...]:
    return interiors(parse_grammar(source, GBNF_FLAVOUR))


def test_the_native_json_grammar_derives_the_quoted_string():
    """``string ::= quote char* quote`` with a backslash-led escape arm."""
    assert interiors(JSON_GRAMMAR) == (Interior('"', "\\"),)


@pytest.mark.parametrize("name", JSON_FORMULATIONS)
def test_every_json_formulation_derives_the_same_interior(name: str):
    """No privileged formulation: the shape is what is read, not the file."""
    path = GROUND_TRUTH / name
    if not path.exists():
        pytest.skip(f"fixture absent: {name}")
    assert interiors(compile_from_path(path).grammar) == (Interior('"', "\\"),)


def test_a_body_with_no_escape_arm_derives_an_empty_escape():
    """The escape is a fact about the body, not an assumption about quoting."""
    source = 'root ::= str\nstr ::= "\'" body* "\'"\nbody ::= [^\']'
    assert _interiors(source) == (Interior("'", ""),)


def test_the_escape_is_the_char_a_two_item_body_arm_leads_with():
    """``char ::= unescaped | "\\\\" escape`` — the second arm's lead."""
    source = (
        'root ::= str\nstr ::= "\'" char* "\'"\n'
        "char ::= unescaped | \"~\" escape\nunescaped ::= [^'~]\nescape ::= ['~]"
    )
    assert _interiors(source) == (Interior("'", "~"),)


def test_a_rule_whose_delimiters_differ_is_not_an_interior():
    """An interior is opened and closed by the SAME character; a bracket pair
    is a region to divide, not a span to skip."""
    assert _interiors('root ::= "(" body* ")"\nbody ::= [^()]') == ()


def test_a_bounded_body_is_not_an_interior():
    """Nothing is skipped whole unless the body repeats without bound."""
    assert _interiors('root ::= "\'" body "\'"\nbody ::= [^\']') == ()


def test_an_inline_body_is_not_an_interior():
    """The body must be a named rule — the escape is read from its arms."""
    assert _interiors('root ::= "\'" [^\']* "\'"') == ()


def test_a_multi_arm_rule_is_not_an_interior():
    """A choice has no single delimited shape to read."""
    source = 'root ::= str\nstr ::= "\'" body* "\'" | "x"\nbody ::= [^\']'
    assert _interiors(source) == ()


def test_a_grammar_with_no_delimited_region_derives_none():
    """Empty is the honest answer, and the scan's cue to watch nothing."""
    assert _interiors('root ::= item+\nitem ::= [a-z]+ "\\n"') == ()


def test_the_analysis_is_memoised_per_grammar_identity():
    """The same object answers from the memo; an equal one recomputes — the
    strong reference in the memo is what stops a recycled id aliasing."""
    grammar = parse_grammar(
        'root ::= str\nstr ::= "\'" b* "\'"\nb ::= [^\']', GBNF_FLAVOUR
    )
    assert interiors(grammar) is interiors(grammar)
