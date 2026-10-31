"""Tests for lexic.parsing.pda.analysis.gates.ends.sites — the contexts a loop
reads its run's end in, and the cascade step that settles a loop there.

The witness is a loop whose rule is referenced twice: before ``;``, where
nothing needs the run, and at the end of a repeated tail, where the next
item's own run of the same class does. Only the second reads anything.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.ends.leads import FREE, FULL, Reach
from lexic.parsing.pda.analysis.gates.ends.sites import CONTEXT_CAP, RunIndex, RunSites
from lexic.parsing.pda.core.charsets import CharSet

AZ = CharSet(frozenset("abcdefghijklmnopqrstuvwxyz"))
WITNESS = 'root ::= entry+\nentry ::= e ";" tail*\ntail ::= "," e\ne ::= [a-z]+\n'


def _lifted(text: str) -> IrAst:
    """The lifted codegen grammar the analysis runs over."""
    return lift_optional_nullables(compile_text(text).codegen_grammar)


def _sites(text: str, delegated: bool = False) -> tuple[RunSites, int]:
    """``e``'s run sites for ``[a-z]``, and its loop's key."""
    grammar = _lifted(text)
    rules = {str(rule.name): rule for rule in grammar.rules}
    sites = RunIndex(rules, str(grammar.start), delegated).of(AZ)
    (key,) = sites.loops
    return sites, key


def _semis(sites: RunSites, key: int) -> set[Reach]:
    """Where ``;`` stands in each context the loop is read in."""
    out = set()
    for lead in sites.loop_contexts(key):
        assert lead is not None
        out.update(reach for chars, reach in lead.marks if chars.has(";"))
    return out


def test_the_loop_is_read_in_each_context_its_rule_is_cloned_for() -> None:
    """Before ``;`` the run is all the loop's; at a tail's end the next entry
    needs at least one of it before its ``;``."""
    sites, key = _sites(WITNESS)
    assert _semis(sites, key) == {Reach(0, FULL), Reach(1, FREE)}
    assert sites.decides(key, known=True)


def test_an_island_interior_does_not_know_what_follows_its_end() -> None:
    """A delegate's start is not the document's end: anything may follow it,
    ``;`` at once included, so no context there needs any of the run."""
    sites, key = _sites(WITNESS, delegated=True)
    assert None in sites.loop_contexts(key)
    assert not sites.decides(key, known=True)
    assert not sites.decides(key, known=False)


def test_contexts_that_keep_multiplying_are_refused_at_the_cap() -> None:
    """Each nesting level needs one more of the run after it: the contexts
    never close, so the class is refused, not cut at a depth."""
    grammar = 'root ::= x ";"\nx ::= "(" x [a-z] | [a-z]*\n'
    sites, key = _sites(grammar)
    assert not sites.decides(key, known=False)
    assert sites.refused
    analysis = GrammarAnalysis(_lifted(grammar))
    notes = [note for notes in analysis.demoted.values() for note in notes]
    notes += [note for notes in analysis.conflicts.values() for note in notes]
    assert any(f"past {CONTEXT_CAP}" in note for note in notes)


def test_the_witness_loop_is_decided_where_its_run_ends() -> None:
    """The cascade files the run-end decision, not the longest take."""
    analysis = GrammarAnalysis(_lifted(WITNESS))
    assert analysis.demoted["e"] == ["e[0]: loop stop-set applied (run end)"]
    assert len(analysis.taxonomy.loops.run) == 1


def test_a_loop_its_own_arm_still_needs_text_after_keeps_its_route() -> None:
    """``[a-z]* [a-z]``: the rest of the arm is not nullable, so the loop is
    not settled at its run's end and ``e`` islands as before."""
    grammar = (
        'root ::= entry+\nentry ::= e ";" tail*\ntail ::= "," e\ne ::= [a-z]* [a-z]\n'
    )
    analysis = GrammarAnalysis(_lifted(grammar))
    assert not analysis.taxonomy.loops.run
    assert "e" in analysis.conflicts


def test_an_unclosed_follower_keeps_the_longest_take() -> None:
    """``[0-9] [a-z]* ";"`` leads with a restricted prefix of varying length:
    MIXED, so no context needs any of the run and nothing is decided."""
    grammar = (
        'root ::= item+\nitem ::= head tail*\ntail ::= "," e\n'
        'e ::= [a-z0-9]+\nhead ::= [0-9] [a-z]* ";"\n'
    )
    analysis = GrammarAnalysis(_lifted(grammar))
    assert not analysis.taxonomy.loops.run
    assert analysis.demoted["e"] == ["e[0]: loop stop-set applied (runs longest)"]


def test_an_escaping_stop_set_with_an_unclosed_end_stays_a_fail_island() -> None:
    """``x ::= [a-c]*`` before ``"ab"?``: the input may end after the run or
    two characters later — MIXED, so the escape keeps its engine fallback."""
    analysis = GrammarAnalysis(_lifted('root ::= x "ab"?\nx ::= [a-c]*\n'))
    assert not analysis.taxonomy.loops.run
    assert "x" in analysis.fail_islands
