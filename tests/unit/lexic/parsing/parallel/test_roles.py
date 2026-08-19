"""Tests for ``lexic.parsing.parallel.roles`` — derived anchor roles.

The demonstrable shapes: a bracketing arm derives an opener/closer pair
(trailing noise after the closer allowed), and a repeated body's leading
anchor literal derives a separator (resolving through unit rule refs).
Nothing is hardcoded per formulation — every case here goes through the
standard pipeline.
"""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.parallel import Roles, roles
from tests.unit.lexic.parsing.parallel.test_anchors import JSONISH


def test_jsonish_derives_the_brace_pair_and_comma_separator():
    """``"{" ws member ("," ws member)* "}"`` → pair ``{``/``}``, sep ``,``."""
    got = roles(parse_grammar(JSONISH, GBNF_FLAVOUR))
    assert got.pairs == (("{", "}"),)
    assert got.separators == frozenset(",")


def test_trailing_noise_after_the_closer_is_allowed():
    """The closer is the LAST anchor literal, not the last item."""
    grammar = 'root ::= "(" x ")" ws\nx ::= [a-z]+\nws ::= " "*'
    got = roles(parse_grammar(grammar, GBNF_FLAVOUR))
    assert got.pairs == (("(", ")"),)


def test_separator_resolves_through_unit_rule_refs():
    """``tail ::= comma item`` with ``comma ::= ","`` still derives ``,``."""
    grammar = 'root ::= item tail*\ntail ::= comma item\ncomma ::= ","\nitem ::= [a-z]+'
    got = roles(parse_grammar(grammar, GBNF_FLAVOUR))
    assert got.separators == frozenset(",")


def test_a_grammar_without_the_shapes_derives_empty_roles():
    """No bracketing arm, no repeated separated body — empty roles, not an
    error: the orchestrator's cue for sequential processing."""
    ast = parse_grammar('root ::= x y\nx ::= "ab"\ny ::= "ba"', GBNF_FLAVOUR)
    assert roles(ast) == Roles((), frozenset())
