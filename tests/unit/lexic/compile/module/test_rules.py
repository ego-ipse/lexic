"""Tests for compile/module/rules.py — the module self-grammar's statement skeleton.

``module_grammar()`` merges the statement skeleton with the notation's own
rules. Moved here byte-for-byte from ``test_selfgrammar.py``, where these six
tests lived before ``module_grammar`` moved out of ``selfgrammar.py`` into its
own module; ``selfgrammar.py`` still re-exports the symbol and keeps its own
tests for ``parse_module``/``verify_module``.
"""

from __future__ import annotations

from lexic.compile.module.rules import module_grammar
from lexic.compile.notation.parse import NOTATION_GRAMMAR
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis

# ── module_grammar() shape pins ─────────────────────────────────────────


def test_module_grammar_starts_at_m_module():
    """The merged grammar's start rule is the statement-skeleton root."""
    assert module_grammar().start == "m-module"


def test_module_grammar_merges_m_rules_with_notation_rules_minus_start():
    """The rule set is the m-prefixed statement rules plus every notation
    rule EXCEPT notation's own "start" (the module skeleton supplies its own
    top-level rule instead), plus the module's own ``ws-inl`` (space/tab-only
    trailing whitespace the swapped notation token rules point at)."""
    grammar = module_grammar()
    names = [str(rule.name) for rule in grammar.rules]
    m_names = {n for n in names if n.startswith("m-")}
    non_m_names = {n for n in names if not n.startswith("m-")}
    notation_names = {
        str(rule.name) for rule in NOTATION_GRAMMAR.rules if str(rule.name) != "start"
    }
    assert non_m_names == notation_names | {"ws-inl"}
    assert "start" not in names
    assert m_names  # the statement skeleton contributed rules too


def test_module_grammar_island_set_is_the_lone_m_imports_island():
    """Complete-β pin (the value-final-newline fix): the six notation token
    rules' trailing ``ws`` is rewritten to newline-free ``ws-inl`` and the
    two grammar statements own an explicit ``m-nl``, so ``name`` and ``ws``
    de-island (FOLLOW(name) is now identifier-free). Only the benign
    once-per-file ``m-imports`` island remains."""
    analysis = GrammarAnalysis(lift_optional_nullables(module_grammar()))
    assert sorted(analysis.islands) == ["m-imports"]
    assert not analysis.fail_islands


def test_module_grammar_has_no_duplicate_rule_names():
    """m-rule names and notation rule names never collide (concatenation,
    not merge-by-name)."""
    grammar = module_grammar()
    names = [str(rule.name) for rule in grammar.rules]
    assert len(names) == len(set(names))


def test_m_gap_is_non_semantic():
    """m-gap (blank-line runs) is structural noise, not semantic content."""
    grammar = module_grammar()
    gap = next(r for r in grammar.rules if str(r.name) == "m-gap")
    assert gap.semantic is False


def test_ws_inl_is_non_semantic_and_newline_free():
    """ws-inl (the swapped token rules' trailing whitespace) is structural
    noise over space/tab only — never a newline, so a value-final token
    stops at the newline its statement owns."""
    grammar = module_grammar()
    ws_inl = next(r for r in grammar.rules if str(r.name) == "ws-inl")
    assert ws_inl.semantic is False
    members = ws_inl.body[0][0].atom.members()
    assert ord("\n") not in members
    assert ord(" ") in members and ord("\t") in members
