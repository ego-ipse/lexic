"""Tests for lexic.parsing.pda.compiler.eligibility — what the clone compiler ASKS.

``extent_consult`` must prove against the clone's hard continuation unioned
with the rule's soft FOLLOW, not the hard continuation alone. On
``root ::= word gap "z"; word ::= "x" [a-b]+ "q"?; gap ::= "q"*``, the
clone's tail is ``{z}`` and the rule's real soft FOLLOW is ``{q, z}`` —
proving against ``{z}`` alone wrongly licenses a consult (the ``"q"?`` could
steal ``gap``'s ``q``), and the union correctly declines. Both calls run
through the same public function so the test fails if the union is ever
dropped back to the tail alone.
"""

from __future__ import annotations

from lexic.compile import canonical_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.pda.compiler.eligibility import (
    extent_consult,
    extent_pattern,
    matches_own_text,
)
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.product.abi.construction import Construction
from lexic.parsing.product.regular import prove_regular
from lexic.parsing.product.routines import RuleRoutine


def _rules(source: str) -> dict:
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in ast.rules}


def _matched_routine(field: str) -> RuleRoutine:
    construction = Construction(lambda **kw: kw, (), frozenset(), matched=field)
    return RuleRoutine(0, (), 0, -1, construction)


# ── matches_own_text ──────────────────────────────────────────────────────


def test_matches_own_text_is_false_for_a_transparent_clone():
    """A clone with no routine at all (an inline group) has nothing to match."""
    assert matches_own_text(None) is False


def test_matches_own_text_is_false_without_a_matched_field():
    """A construction that fills no field from the rule's own extent."""
    routine = _matched_routine("")
    assert matches_own_text(routine) is False


def test_matches_own_text_is_false_when_construction_itself_is_none():
    """A pass-through routine (construction=None) is not a value_str shape."""
    routine = RuleRoutine(0, (), 0, 0, None)
    assert matches_own_text(routine) is False


def test_matches_own_text_is_true_with_a_declared_matched_field():
    """The value_str shape: a construction that fills a field from the whole
    matched extent."""
    routine = _matched_routine("value")
    assert matches_own_text(routine) is True


# ── extent_consult: match_only gates everything ──────────────────────────


def test_extent_consult_declines_outright_when_not_match_only():
    """A rule whose value is not its own text has no whole-extent question."""
    rules = _rules('root ::= word "z"\nword ::= "a"\n')
    result = extent_consult(
        rules, "word", False, CharSet.from_chars("z"), CharSet.EMPTY
    )
    assert result is None


# ── the live defect: tail alone WRONGLY proves; tail ∪ follow declines ────

_NULLABLE_FOLLOWER = 'root ::= word gap "z"\nword ::= "x" [a-b]+ "q"?\ngap ::= "q"*\n'


def test_extent_consult_on_the_tail_alone_wrongly_proves():
    """Reproducing the OLD (buggy) question directly: against {z} alone, the
    proof cannot see that word's trailing "q"? could steal gap's "q" — so it
    proves when it should not. This is the control that shows the union in
    the next test is doing real work, not just narrowing an already-failing
    case."""
    rules = _rules(_NULLABLE_FOLLOWER)
    tail_alone = CharSet.from_chars("z")
    result = extent_consult(rules, "word", True, tail_alone, CharSet.EMPTY)
    assert result is not None


def test_extent_consult_unions_the_tail_with_the_rules_soft_follow():
    """The real question: {z} ∪ {q, z} = {q, z} — now obligation 3 sees the
    stolen "q" and correctly declines."""
    rules = _rules(_NULLABLE_FOLLOWER)
    tail = CharSet.from_chars("z")
    follow = CharSet.from_chars("q", "z")
    result = extent_consult(rules, "word", True, tail, follow)
    assert result is None


def test_extent_consult_agrees_with_prove_regular_over_the_unioned_charset():
    """extent_consult is exactly prove_regular(rules, name, tail | follow) —
    pinned by cross-checking against the lower-level function directly."""
    rules = _rules('root ::= word "z"\nword ::= "a"+\n')
    tail = CharSet.from_chars("z")
    follow = CharSet.from_chars("y")
    via_eligibility = extent_consult(rules, "word", True, tail, follow)
    via_regular = prove_regular(rules, "word", tail.union(follow))
    assert (via_eligibility is None) == (via_regular is None)


# ── extent_pattern: the proof's OWN entry, not the closure's ────────────


def test_extent_pattern_returns_the_proofs_own_root_entry():
    """A closure of three rules (word, a, b) — extent_pattern must return
    WORD's pattern, never a or b's, even though all three share one
    recognizer and one pattern table."""
    rules = _rules('root ::= word "z"\nword ::= a b\na ::= "p"\nb ::= "x"\n')
    proof = prove_regular(rules, "word", CharSet.from_chars("z"))
    assert proof is not None
    assert len(proof.recognizer.index) > 1  # a genuinely shared closure
    pattern = extent_pattern(proof)
    assert pattern is proof.recognizer.pats[proof.recognizer.index["word"]]
    for other in ("a", "b"):
        assert pattern is not proof.recognizer.pats[proof.recognizer.index[other]]
