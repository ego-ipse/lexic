"""Tests for lexic.grammars.gbnf.grammar_tail — the late canonical GBNF rules.

Composed-grammar coverage (rule count, every ruleref resolved) lives in
``tests/unit/lexic/grammars/test_gbnf.py``; this file targets the tail
table's own shape and a couple of its terminal char classes directly.
"""

from __future__ import annotations

from lexic.grammars.gbnf.grammar_tail import GBNF_TAIL
from lexic.ir import IrCharClass, IrRule


def test_gbnf_tail_is_a_tuple_of_rules_with_unique_names():
    """Every entry is an IrRule and no rule name repeats."""
    assert all(isinstance(rule, IrRule) for rule in GBNF_TAIL)
    names = [str(rule.name) for rule in GBNF_TAIL]
    assert len(names) == len(set(names))


def test_gbnf_tail_defines_the_expected_rule_names():
    """The tail table defines the documented late rule names."""
    names = {str(rule.name) for rule in GBNF_TAIL}
    assert {"digit", "q-tail", "hexch", "cc-esc", "cc-other"} <= names


def test_digit_rule_matches_a_single_ascii_digit_character_class():
    """``digit`` covers exactly the ten ASCII digit code points."""
    digit = next(rule for rule in GBNF_TAIL if str(rule.name) == "digit")
    charclass = digit.body[0][0].atom
    assert isinstance(charclass, IrCharClass)
    members = set(charclass.members())
    assert {ord(c) for c in "0123456789"} == members


def test_hexch_rule_accepts_both_cases_of_a_to_f():
    """``hexch`` covers 0-9 and both cases of a-f, and nothing past ``f``."""
    hexch = next(rule for rule in GBNF_TAIL if str(rule.name) == "hexch")
    charclass = hexch.body[0][0].atom
    assert isinstance(charclass, IrCharClass)
    members = set(charclass.members())
    assert {ord(c) for c in "0123456789abcdefABCDEF"} == members
    assert ord("g") not in members
