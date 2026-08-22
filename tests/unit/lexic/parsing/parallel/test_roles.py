"""Tests for ``lexic.parsing.parallel.roles`` — derived anchor roles.

The demonstrable shapes: a bracketing arm derives an opener/closer pair
(trailing noise after the closer allowed), and a repeated body's leading
anchor literal derives a separator (resolving through unit rule refs).
Nothing is hardcoded per formulation — every case here goes through the
standard pipeline.
"""

from __future__ import annotations

import lexic.parsing
from lexic.compile import compile_text, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing import parallel
from lexic.parsing.parallel import Roles, Separator, roles
from lexic.parsing.parallel.roles import Terminator
from tests.unit.lexic.parsing.parallel.discovery.test_anchors import JSONISH


def test_the_facade_exports_the_parallel_vocabulary():
    """Every name in ``__all__`` resolves on the package."""
    for name in parallel.__all__:
        assert getattr(parallel, name) is not None


def test_the_parsing_root_does_not_reexport_the_parallel_layer():
    """Neither engine consumes these names — they stay off the root."""
    assert "anchors" not in lexic.parsing.__all__
    assert "worker_count" not in lexic.parsing.__all__


def test_jsonish_derives_the_brace_pair_and_comma_separator():
    """``"{" ws member ("," ws member)* "}"`` → pair ``{``/``}``, sep ``,``."""
    got = roles(parse_grammar(JSONISH, GBNF_FLAVOUR))
    assert got.pairs == (("{", "}"),)
    assert got.separators == frozenset(",")


def test_trailing_noise_after_the_closer_is_allowed():
    """The closer is the LAST anchor literal, not the last item."""
    grammar = 'root ::= "(" x ")" ws\nx ::= [a-z]+\nws ::= " "*'
    got = roles(compile_text(grammar).codegen_grammar)
    assert got.pairs == (("(", ")"),)


def test_separator_records_carry_the_orchestration_rules():
    """``tail ::= comma item`` derives the full record: char, container,
    repeated item, and the lead rule the cut text re-parses under."""
    grammar = 'root ::= item tail*\ntail ::= comma item\ncomma ::= ","\nitem ::= [a-z]+'
    got = roles(parse_grammar(grammar, GBNF_FLAVOUR))
    assert got.separators == frozenset(",")
    assert got.records == (Separator(",", "root", "tail", "comma"),)


def test_a_common_terminator_resolves_through_recursive_rule_refs():
    """Every entry arm reaches the same newline through ``ending`` and ``nl``."""
    grammar = (
        "root ::= entry+\n"
        "entry ::= word ending\n"
        'word ::= "a" | "b"\n'
        "ending ::= nl\n"
        'nl ::= "\\n"\n'
    )

    got = roles(parse_grammar(grammar, GBNF_FLAVOUR))
    assert got.terminators == (Terminator("\n", "root", "entry"),)


def test_finite_anchor_class_derives_each_separator_alternative():
    """A compiled ``+ | -`` lead remains two structural separator choices."""
    grammar = (
        "root ::= expr\n"
        "expr ::= number tail*\n"
        "tail ::= addop number\n"
        'addop ::= "+" | "-"\n'
        "number ::= [0-9]+\n"
    )

    got = roles(compile_text(grammar).codegen_grammar)
    assert got.records == (
        Separator("+", "expr", "tail", "addop"),
        Separator("-", "expr", "tail", "addop"),
    )


def test_a_grammar_without_the_shapes_derives_empty_roles():
    """No bracketing arm, no repeated separated body — empty roles, not an
    error: the orchestrator's cue for sequential processing."""
    ast = parse_grammar('root ::= x y\nx ::= "ab"\ny ::= "ba"', GBNF_FLAVOUR)
    assert roles(ast) == Roles((), ())
