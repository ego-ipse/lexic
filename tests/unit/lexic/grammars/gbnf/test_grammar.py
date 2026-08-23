"""Tests for lexic.grammars.gbnf.grammar — the native GBNF self-grammar root.

Full rule-count, rule-name and ruleref-resolution coverage lives in
``tests/unit/lexic/grammars/test_gbnf.py``; this file targets the module's
own contribution: assembling ``GBNF_GRAMMAR`` from its early rules plus the
late rules imported from :mod:`lexic.grammars.gbnf.grammar_tail`.
"""

from __future__ import annotations

from lexic.grammars.gbnf.grammar import GBNF_GRAMMAR
from lexic.grammars.gbnf.grammar_tail import GBNF_TAIL
from lexic.ir import IrAst


def test_gbnf_grammar_is_an_irast_starting_at_grammar():
    """The assembled self-grammar is an IrAst rooted at ``grammar``."""
    assert isinstance(GBNF_GRAMMAR, IrAst)
    assert GBNF_GRAMMAR.start == "grammar"


def test_gbnf_grammar_includes_every_tail_rule():
    """Every rule GBNF_TAIL defines is present in the assembled grammar."""
    names = {str(rule.name) for rule in GBNF_GRAMMAR.rules}
    tail_names = {str(rule.name) for rule in GBNF_TAIL}
    assert tail_names <= names


def test_gbnf_grammar_tail_rules_come_after_the_early_rules_in_declaration_order():
    """The tail rules appear as one contiguous, order-preserved block."""
    names = [str(rule.name) for rule in GBNF_GRAMMAR.rules]
    tail_names = [str(rule.name) for rule in GBNF_TAIL]
    tail_start = names.index(tail_names[0])
    assert names[tail_start : tail_start + len(tail_names)] == tail_names
