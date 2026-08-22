"""Tests for ``lexic.parsing.parallel.discovery.shapes`` — the arm-shape questions.

Three facts the split analyses ask a grammar for: what an item spells,
whether it repeats, and what every arm of an alternation carries at one end.
Every case here goes through the standard pipeline — nothing is hardcoded per
formulation.
"""

from __future__ import annotations

from functools import partial

from lexic.compile import parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAlternation, IrAst, IrItem, IrRule
from lexic.parsing.parallel.discovery.shapes import (
    UNIT,
    derives_empty,
    edge_char,
    leads_with,
    literal_char,
    unbounded,
)


def _rule_map(source: str) -> dict[str, IrRule]:
    grammar: IrAst = parse_grammar(source, GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in grammar.rules}


def _arm_items(rule_map: dict[str, IrRule], name: str) -> tuple[IrItem, ...]:
    return tuple(tuple(rule_map[name].body)[0])


def _body(rule_map: dict[str, IrRule], name: str) -> IrAlternation:
    return rule_map[name].body


# ── unbounded ─────────────────────────────────────────────────────────────


def test_a_starred_item_is_unbounded():
    """``x*`` has no upper bound."""
    items = _arm_items(_rule_map('root ::= x*\nx ::= "a"'), "root")
    assert unbounded(items[0])


def test_a_plussed_item_is_unbounded():
    """``x+`` has no upper bound either — ``lo`` is not what is asked."""
    items = _arm_items(_rule_map('root ::= x+\nx ::= "a"'), "root")
    assert unbounded(items[0])


def test_a_unit_item_is_not_unbounded():
    """Exactly-once is bounded above."""
    items = _arm_items(_rule_map('root ::= x\nx ::= "a"'), "root")
    assert not unbounded(items[0])
    assert items[0].quantifier == UNIT


def test_an_optional_item_is_not_unbounded():
    """``x?`` is bounded above at one."""
    items = _arm_items(_rule_map('root ::= x?\nx ::= "a"'), "root")
    assert not unbounded(items[0])


# ── literal_char ──────────────────────────────────────────────────────────


def test_a_single_char_literal_spells_that_char():
    """The direct case: the item IS the character."""
    rule_map = _rule_map('root ::= "{" x\nx ::= "a"')
    assert literal_char(_arm_items(rule_map, "root")[0], rule_map) == "{"


def test_a_multi_char_literal_spells_nothing():
    """A split point is one character; two is not a character."""
    rule_map = _rule_map('root ::= "{{" x\nx ::= "a"')
    assert literal_char(_arm_items(rule_map, "root")[0], rule_map) is None


def test_a_named_punctuation_rule_resolves_through_its_reference():
    """``begin-object ::= ws "{" ws`` — a rule spells one character when
    exactly one of its items does, so punctuation may be named and may sit
    among noise."""
    rule_map = _rule_map(
        'root ::= begin-object x\nbegin-object ::= ws "{" ws\nws ::= " "*\nx ::= "a"'
    )
    assert literal_char(_arm_items(rule_map, "root")[0], rule_map) == "{"


def test_a_rule_spelling_two_characters_spells_neither():
    """Two spelled items in the target leave the reference ambiguous."""
    rule_map = _rule_map('root ::= pair x\npair ::= "{" "}"\nx ::= "a"')
    assert literal_char(_arm_items(rule_map, "root")[0], rule_map) is None


def test_a_repeated_item_spells_nothing():
    """Only a unit-quantified occurrence stands for one character."""
    rule_map = _rule_map('root ::= "{"* x\nx ::= "a"')
    assert literal_char(_arm_items(rule_map, "root")[0], rule_map) is None


def test_a_multi_arm_rule_reference_spells_nothing():
    """A choice is not a spelling."""
    rule_map = _rule_map('root ::= brace x\nbrace ::= "{" | "}"\nx ::= "a"')
    assert literal_char(_arm_items(rule_map, "root")[0], rule_map) is None


def test_a_char_class_spells_nothing():
    """A class is a set, not a character."""
    rule_map = _rule_map('root ::= [a-z] x\nx ::= "a"')
    assert literal_char(_arm_items(rule_map, "root")[0], rule_map) is None


def test_an_unresolvable_reference_spells_nothing():
    """A reference with no rule in the map resolves to nothing, not a raise —
    the analyses run over sub-grammars and must tolerate a dangling name."""
    rule_map = _rule_map('root ::= x\nx ::= "a"')
    assert literal_char(_arm_items(rule_map, "root")[0], {}) is None


# ── edge_char ─────────────────────────────────────────────────────────────


def test_every_arm_leading_with_the_same_char_agrees():
    """``"," a | "," b`` leads with ``,`` however the arms continue."""
    rule_map = _rule_map('root ::= item\nitem ::= "," a | "," b\na ::= "x"\nb ::= "y"')
    spells = partial(literal_char, rule_map=rule_map)
    assert edge_char(_body(rule_map, "item"), 0, spells) == ","


def test_arms_leading_with_different_chars_agree_on_nothing():
    """Disagreement is ``None``, never one of the two."""
    rule_map = _rule_map('root ::= item\nitem ::= "," a | ";" a\na ::= "x"')
    spells = partial(literal_char, rule_map=rule_map)
    assert edge_char(_body(rule_map, "item"), 0, spells) is None


def test_the_last_index_reads_what_every_arm_ends_with():
    """``at=-1`` is the terminator question, the same walk from the other end."""
    rule_map = _rule_map('root ::= item\nitem ::= a ";" | b ";"\na ::= "x"\nb ::= "y"')
    spells = partial(literal_char, rule_map=rule_map)
    assert edge_char(_body(rule_map, "item"), -1, spells) == ";"
    assert edge_char(_body(rule_map, "item"), 0, spells) is None


def test_an_arm_spelling_nothing_at_the_edge_defeats_agreement():
    """One arm that spells nothing there is enough — agreement is unanimous."""
    rule_map = _rule_map('root ::= item\nitem ::= "," a | [a-z] a\na ::= "x"')
    spells = partial(literal_char, rule_map=rule_map)
    assert edge_char(_body(rule_map, "item"), 0, spells) is None


def test_an_empty_alternation_body_agrees_on_nothing():
    """No arms, nothing carried — ``None``, not a raise."""
    spells = partial(literal_char, rule_map={})
    assert edge_char(IrAlternation(), 0, spells) is None


# ── leads_with / derives_empty ──────────────────────────────────────────


def test_a_left_recursive_arm_leads_with_every_character_conservatively():
    """An arm that opens by referencing its own rule never resolves a first
    character, so the unresolved cycle answers yes for ANY character — the
    safe direction, since an unprovable arm must not certify a sole leading
    spelling for a caller like ``_unit_anchored``."""
    rule_map = _rule_map('root ::= x\nx ::= x "a" | "b"')
    items = _arm_items(rule_map, "x")  # x's first arm: x "a"
    assert leads_with(items, "z", rule_map, frozenset())
    assert leads_with(items, "q", rule_map, frozenset())


def test_a_nullable_prefix_lets_the_scan_reach_the_next_items_lead():
    """``ws?`` can derive empty, so the arm's leading-character question is
    answered by what FOLLOWS it, not by the optional item alone."""
    rule_map = _rule_map('root ::= item\nitem ::= ws? "!"\nws ::= " "')
    items = _arm_items(rule_map, "item")
    assert leads_with(items, "!", rule_map, frozenset())


def test_a_cyclic_rule_derives_empty_conservatively():
    """A rule whose only arm is a bare self-reference never proves it is
    non-empty either, so the unresolved cycle answers yes here too — more
    candidate leading arms for ``leads_with`` to scan past, not fewer."""
    rule_map = _rule_map("root ::= loop\nloop ::= loop")
    item = _arm_items(rule_map, "loop")[0]
    assert derives_empty(item, rule_map, frozenset())
