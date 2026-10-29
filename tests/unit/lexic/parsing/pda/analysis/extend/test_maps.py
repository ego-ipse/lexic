"""Tests for lexic.parsing.pda.analysis.extend.maps — the fixpoints' working maps,
and the atom bodies EXTEND and NON_INITIAL share."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrCharClass, IrChr, IrLiteral, IrRuleRef
from lexic.parsing.pda.analysis.extend.inner import NON_INITIAL
from lexic.parsing.pda.analysis.extend.lengthen import EXTEND
from lexic.parsing.pda.analysis.extend.maps import (
    Extensions,
    anything,
    found_ruleref,
    nothing,
)
from lexic.parsing.pda.analysis.predicates import rule_alphabets
from lexic.parsing.pda.core.charsets import CharSet

SOURCE = 'x ::= "ab" y\ny ::= [0-9]+\n'


def _maps() -> Extensions:
    grammar = compile_text(SOURCE, cache_key="extend-maps").codegen_grammar
    return Extensions.empty({str(one.name): one for one in grammar.rules})


def test_a_fixpoint_starts_every_rule_empty_beside_its_alphabet() -> None:
    """The start is the least element: every rule's set empty, and the ALPHABET
    each set falls back to read from the same rules."""
    grammar = compile_text(SOURCE, cache_key="extend-maps").codegen_grammar
    rules = {str(one.name): one for one in grammar.rules}
    maps = Extensions.empty(rules)
    assert set(maps.found) == set(rules)
    assert all(found == CharSet.EMPTY for found in maps.found.values())
    assert maps.alphabets == rule_alphabets(rules)


def test_a_rule_reference_reads_its_target_as_it_stands_and_an_unknown_is_any() -> None:
    """``found_ruleref`` answers from the CURRENT maps, so a fixpoint step sees
    what the rule has grown to; a name the grammar does not define is ANY."""
    maps = _maps()
    maps.found["y"] = CharSet.from_chars("7")
    assert found_ruleref(None, IrRuleRef("y"), maps) == CharSet.from_chars("7")
    assert found_ruleref(None, IrRuleRef("undefined"), maps) == CharSet.ANY


def test_the_closed_and_the_unenumerable_bodies() -> None:
    """A single string extends by nothing; a token atom by anything."""
    assert nothing(None, IrLiteral("ab"), ()) == CharSet.EMPTY
    assert anything(None, IrLiteral("ab"), ()) == CharSet.ANY


def test_both_tables_route_a_shared_atom_to_the_same_body() -> None:
    """The bodies are shared, not copied: EXTEND and NON_INITIAL both send a
    character class to ``nothing`` and a rule reference to ``found_ruleref``."""
    maps = _maps()
    maps.found["y"] = CharSet.from_chars("3")
    charclass, ref = IrCharClass(IrChr("a")), IrRuleRef("y")
    for table in (EXTEND, NON_INITIAL):
        assert table.resolve(charclass).eval(None, charclass, maps) == CharSet.EMPTY
        assert table.resolve(ref).eval(None, ref, maps) == CharSet.from_chars("3")
