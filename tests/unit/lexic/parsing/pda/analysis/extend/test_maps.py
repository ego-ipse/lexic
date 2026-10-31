"""Tests for lexic.parsing.pda.analysis.extend.maps — the fixpoints' working maps,
and the atom bodies EXTEND and NON_INITIAL share."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrCharClass, IrChr, IrItem, IrLiteral, IrRuleRef
from lexic.parsing.pda.analysis.extend.inner import NON_INITIAL
from lexic.parsing.pda.analysis.extend.lengthen import EXTEND
from lexic.parsing.pda.analysis.extend.maps import (
    Confinement,
    Extensions,
    Solve,
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


def test_reopening_drops_only_what_the_maps_could_refute() -> None:
    """TAILS and the True verdicts go, the False ones stay, and each dropped
    verdict comes back as the site and index to re-ask it at."""
    memo = Confinement.empty()
    arm: tuple[IrItem, ...] = ()
    memo.tails[("y", CharSet.EMPTY)] = CharSet.ANY
    memo.verdicts[(1, 0)] = (arm, True)
    memo.verdicts[(2, 0)] = (arm, False)
    assert memo.reopen() == [(arm, 0)]
    assert not memo.tails and memo.verdicts == {(2, 0): (arm, False)}
    assert not memo.reopen()


def test_a_verdict_is_kept_for_the_pass_while_a_solve_is_under_way() -> None:
    """Inside a solve a verdict is kept for the solve's pass alone, since TAILS
    may still grow; outside one, for the build. Either is read back only at
    the site it was asked at."""
    memo = Confinement.empty()
    site: tuple[IrItem, ...] = ()
    other: tuple[IrItem, ...] = ()
    memo.solve.append(Solve([], set(), set(), {}))
    memo.keep((1, 0), site, True)
    assert not memo.verdicts and memo.verdict((1, 0), site) is True
    memo.solve.clear()
    memo.keep((2, 0), site, False)
    assert memo.verdicts == {(2, 0): (site, False)}
    assert memo.verdict((2, 0), site) is False
    assert memo.verdict((2, 0), [*other]) is None
