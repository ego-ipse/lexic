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
    exact_text,
    item_lead,
    last_charset,
    leads_with,
    literal_char,
    literal_text,
    rule_emits,
    rule_spells,
    sole_char,
    unbounded,
)
from lexic.parsing.pda.core.charsets import CharSet


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


# ── item_lead ─────────────────────────────────────────────────────────────


def test_item_lead_is_the_first_character_of_a_multi_character_literal():
    """A region's opening is entered at its lead character and skipped
    whole, so ``"<["`` contributes only ``"<"`` — the fact that lets a
    sibling ``"["`` region certify beside it."""
    rule_map = _rule_map('root ::= x y\nx ::= "<[" \ny ::= "a"')
    assert item_lead(_arm_items(rule_map, "root")[0], rule_map) == "<"


def test_item_lead_agrees_with_literal_char_for_a_single_character_spelling():
    """A one-character spelling's lead is that same character."""
    rule_map = _rule_map('root ::= "{" x\nx ::= "a"')
    item = _arm_items(rule_map, "root")[0]
    assert item_lead(item, rule_map) == literal_char(item, rule_map) == "{"


def test_item_lead_is_none_when_the_item_spells_nothing():
    """A class is a set, not a spelling — it has no lead character either."""
    rule_map = _rule_map('root ::= [a-z] x\nx ::= "a"')
    assert item_lead(_arm_items(rule_map, "root")[0], rule_map) is None


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


# ── last_charset / exact_text / sole_char ─────────────────────────────────


def test_last_charset_mirrors_first_through_a_vanishing_tail():
    """``ws?`` can derive empty, so what the arm ENDS with is answered by
    what precedes it — the exact mirror of the leading-character walk."""
    rule_map = _rule_map('root ::= item\nitem ::= "!" ws?\nws ::= " "')
    items = _arm_items(rule_map, "item")
    ending = last_charset(items, rule_map, frozenset())
    assert ending.has("!") and ending.has(" ")


def test_last_charset_answers_any_on_an_unresolved_cycle():
    """A cycle it cannot resolve reads as every character, so a caller
    proving a junction CANNOT assemble is never misled into certifying."""
    rule_map = _rule_map('root ::= x\nx ::= "a" x')
    assert last_charset(_arm_items(rule_map, "x"), rule_map, frozenset()) == CharSet.ANY


def test_exact_text_reads_a_whole_reference_chain_but_refuses_noise():
    """``blank ::= nl`` with ``nl ::= "\\n"`` always derives one newline, so a
    proof may reach past it. ``padded ::= ws "!"`` does not: its width varies,
    and ``literal_text`` — which reads the one anchor among noise — would
    wrongly hand back ``"!"`` for a caller asking what the item always spells."""
    rule_map = _rule_map(
        'root ::= blank padded\nblank ::= nl\nnl ::= "\\n"\npadded ::= ws "!"\nws ::= " "*'
    )
    items = _arm_items(rule_map, "root")
    assert exact_text(items[0], rule_map, frozenset()) == "\n"
    assert literal_text(items[1], rule_map) == "!"
    assert exact_text(items[1], rule_map, frozenset()) == ""


def test_sole_char_refuses_a_wider_or_negated_set():
    """Only one positive character turns "can end with" into "always ends
    with"; anything else ends more than one way and proves nothing."""
    assert sole_char(CharSet.from_chars("\n")) == "\n"
    assert sole_char(CharSet.from_chars("a", "b")) == ""
    assert sole_char(CharSet.ANY) == ""
    assert sole_char(CharSet.EMPTY) == ""


# ── rule_spells: the assembly analysis ────────────────────────────────────


def _spells(source: str, rule: str, mark: str) -> bool:
    rule_map = _rule_map(source)
    return rule_spells(rule_map[rule], mark, rule_map, frozenset(), frozenset({rule}))


_ASSEMBLING = 'root ::= para\npara ::= line+\nline ::= [a-z]* "\\n"\n'
"""Lines may be EMPTY, so two of them stand as ``"\\n\\n"`` — the mark no atom
of ``para`` spells and ``para`` derives anyway."""

_SAFE = _ASSEMBLING.replace("[a-z]*", "[a-z]+")
"""Every line opens with a letter, so the junction cannot assemble the mark."""


def test_a_junction_between_repeated_items_spells_the_mark():
    """The assembly obligation itself. Atom-wise emission CERTIFIES this
    owner — no atom of ``para`` spells ``"\\n\\n"`` — and ``para`` derives it
    at the join between two empty lines, so the spelling question must answer
    yes or a cut is admitted the grammar does not have."""
    rule_map = _rule_map(_ASSEMBLING)
    assert not rule_emits(
        rule_map["para"], "\n\n", rule_map, frozenset(), frozenset({"para"})
    )
    assert _spells(_ASSEMBLING, "para", "\n\n")


def test_a_junction_that_cannot_meet_licenses_the_owner():
    """One character apart from the assembling grammar: a line must open with
    a letter, so a line's terminator never meets the next line's opening."""
    assert not _spells(_SAFE, "para", "\n\n")


def test_a_junction_reaches_through_vanishing_items():
    """The items between the two ends may all be empty, and then the ends are
    neighbours. ``mid`` vanishes, so ``head``'s newline meets ``tail``'s."""
    source = (
        "root ::= unit\nunit ::= head mid tail\n"
        'head ::= "a\\n"\nmid ::= " "*\ntail ::= "\\nz"\n'
    )
    assert _spells(source, "unit", "\n\n")


def test_a_repeated_character_class_spells_a_doubled_mark():
    """One occurrence of a class is one character, so the atom cannot spell a
    two-character mark; the quantifier is what puts two of them side by side."""
    assert _spells("root ::= run\nrun ::= [\\n]+\n", "run", "\n\n")
    assert not _spells("root ::= one\none ::= [\\n]\n", "one", "\n\n")


def test_a_mark_wider_than_the_analysis_decides_answers_can_spell():
    """Three characters asks whether derivable text ends with a STRING, which
    is not a character-set question. Undecided answers "can spell", so every
    proof over such a mark declines rather than approximating."""
    assert _spells('root ::= x\nx ::= "q"\n', "x", "abc")


def test_a_one_character_mark_is_exactly_the_emission_question():
    """The delegation that makes the spelling analysis a strict extension:
    at one character it IS ``rule_emits``, line for line."""
    source = 'root ::= x\nx ::= [a-c] "d"\n'
    rule_map = _rule_map(source)
    for char in "abcdz":
        assert rule_spells(
            rule_map["x"], char, rule_map, frozenset(), frozenset({"x"})
        ) == rule_emits(rule_map["x"], char, rule_map, frozenset(), frozenset({"x"}))


def test_an_unresolvable_reference_answers_can_spell():
    """A name the walk cannot resolve reads as able to spell anything — the
    decline direction, as everywhere else in these proofs."""
    grammar: IrAst = parse_grammar('root ::= x\nx ::= missing "a"', GBNF_FLAVOUR)
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    assert rule_spells(rule_map["x"], "ab", rule_map, frozenset(), frozenset({"x"}))
