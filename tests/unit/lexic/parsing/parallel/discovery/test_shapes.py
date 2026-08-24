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
from lexic.ir import IrAlphabet, IrAlternation, IrAst, IrItem, IrLiteral, IrRule
from lexic.parsing.parallel.discovery.shapes import (
    UNIT,
    arm_spells,
    derives_empty,
    edge_char,
    exact_text,
    item_lead,
    item_spells,
    joins,
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


# ── rule_spells: each production mode in isolation, with its negative ─────


def test_a_literal_atom_spells_the_mark_directly():
    """Mode (a): the atom's OWN literal contains the mark whole — no
    junction, no reference, no repetition."""
    assert _spells('root ::= x\nx ::= "a\\n\\nb"\n', "x", "\n\n")


def test_a_literal_atom_with_disjoint_edges_does_not_spell():
    """The matching negative: one newline is not two, and there is nothing
    beside this single item to supply a second character."""
    assert not _spells('root ::= x\nx ::= "a\\nb"\n', "x", "\n\n")


def test_an_item_spells_the_mark_through_its_own_reference():
    """Mode (b): the mark stands inside the rule an item REFERENCES, with no
    junction across items and no repetition — the reference is followed and
    the target's own body answers directly."""
    assert _spells('root ::= x\nx ::= y\ny ::= "a\\n\\nb"\n', "x", "\n\n")


def test_a_referenced_rule_with_disjoint_edges_does_not_spell():
    """The matching negative, one newline apart in the referenced rule."""
    assert not _spells('root ::= x\nx ::= y\ny ::= "a\\nb"\n', "x", "\n\n")


def test_a_direct_junction_between_two_adjacent_items_spells_the_mark():
    """Mode (c): no repetition and no nullable between them — the first
    item's LAST character meets the second item's FIRST character directly,
    the junction clause's plainest shape."""
    assert _spells('root ::= x\nx ::= a b\na ::= "p\\n"\nb ::= "\\nq"\n', "x", "\n\n")


def test_adjacent_items_with_disjoint_edges_do_not_meet():
    """The matching negative: the first item's last character is not the
    mark's head, so the join fails outright."""
    assert not _spells('root ::= x\nx ::= a b\na ::= "p"\nb ::= "\\nq"\n', "x", "\n\n")


def test_joins_directly_reaches_through_nullables_on_both_sides():
    """Mode (c'): ``joins`` in isolation, with TWO vanishing items on each
    side of the split. LAST walks backward past ``n2`` and ``n1`` to find
    ``core``'s real ending character; FIRST walks forward past ``m1`` and
    ``m2`` to find ``tail``'s real opening one — both directions, two
    nullables each, in one join."""
    rule_map = _rule_map(
        "root ::= unit\nunit ::= core n1 n2 m1 m2 tail\n"
        'core ::= "a\\n"\nn1 ::= " "*\nn2 ::= "x"?\n'
        'm1 ::= "y"?\nm2 ::= " "*\ntail ::= "\\nz"\n'
    )
    items = _arm_items(rule_map, "unit")
    before, after = items[:3], items[3:]
    assert joins(before, after, "\n\n", rule_map, frozenset())


def test_joins_through_nullables_refuses_when_the_true_edges_disagree():
    """The matching negative: walking through the same two nullables on each
    side, but the real edges underneath them are not the mark's characters."""
    rule_map = _rule_map(
        "root ::= unit\nunit ::= core n1 n2 m1 m2 tail\n"
        'core ::= "ab"\nn1 ::= " "*\nn2 ::= "x"?\n'
        'm1 ::= "y"?\nm2 ::= " "*\ntail ::= "z"\n'
    )
    items = _arm_items(rule_map, "unit")
    before, after = items[:3], items[3:]
    assert not joins(before, after, "\n\n", rule_map, frozenset())


def test_a_bounded_repetition_spells_a_doubled_mark_at_its_own_join():
    """Mode (d), the bounded case: ``{2,3}`` is bounded ABOVE but still more
    than one — ``repeats()`` reads ``hi > 1``, not merely the absence of an
    upper bound, so a bounded quantifier stands beside itself too."""
    assert _spells("root ::= run\nrun ::= [\\n]{2,3}\n", "run", "\n\n")


def test_a_bounded_repetition_with_disjoint_self_edges_does_not_join():
    """The matching negative: the item repeats, but what it ends with is not
    what it begins with, so two occurrences beside each other never meet as
    the mark — ``repeats() == True`` alone proves nothing."""
    assert not _spells('root ::= run\nrun ::= x{2,3}\nx ::= "a\\n"\n', "run", "\n\n")


# ── conservatism: unknowns, hidden regions, arity, and cycles ─────────────


def test_an_unrecognised_atom_kind_answers_can_spell():
    """``_atom_spells`` recognises literal, class, negation, alternation and
    reference — nothing else. An atom of any other shape (here, a
    token-alphabet binding, constructed directly since no GBNF text produces
    one) falls through to the decline direction: it might spell anything."""
    item = IrItem(IrAlphabet("tokens", IrLiteral("x")))
    assert item_spells(item, "ab", {}, frozenset(), frozenset())


def test_a_hidden_rule_contributes_no_content_but_keeps_its_alphabet():
    """A hidden rule's own SPELLING is excluded from the content question —
    the scan skips its span whole and never reads inside it — but its edge
    alphabet still feeds a junction, because ``joins``/``last_charset``/
    ``first_charset`` read the grammar's real derivations and take no
    ``hidden`` parameter at all. A junction reaching INTO a hidden region
    must stay refused rather than certified."""
    rule_map = _rule_map(
        "root ::= unit\nunit ::= lead veiled tail\n"
        'lead ::= "a\\n"\nveiled ::= "\\n\\n"\ntail ::= "\\nz"\n'
    )
    hidden = frozenset({"veiled"})
    items = _arm_items(rule_map, "unit")

    assert not item_spells(items[1], "\n\n", rule_map, hidden, frozenset())
    assert arm_spells(items, "\n\n", rule_map, hidden, frozenset())


def test_an_empty_arm_never_spells_regardless_of_mark_width():
    """Past ``MARK_ARITY`` the "cannot decide" rule answers ``True`` — except
    an empty arm derives nothing at all, so even that rule has nothing to
    apply to: ``arm_spells`` reads ``bool(items)``, not a bare constant."""
    assert not arm_spells((), "abc", {}, frozenset(), frozenset())


def test_a_cycle_terminates_and_correctly_proves_the_rule_can_spell():
    """One recursive arm cannot resolve through itself and is excluded by
    the path guard (an immediate ``False``, not a probe of the cycle's own
    body), but a SIBLING arm spells the mark directly — the cycle terminates
    rather than looping, and the real answer comes from the other arm."""
    assert _spells('root ::= x\nx ::= x "!" | "\\n\\n"\n', "x", "\n\n")


def test_a_cycle_terminates_and_correctly_proves_the_rule_cannot_spell():
    """Neither arm can ever produce the mark, cyclic or not: the path guard
    stops the recursion at one visit and the conservative ``ANY`` it hands
    back at the join never meets a matching character on the far side, so
    the answer is a real ``False`` rather than a false positive from the
    cycle's own conservatism."""
    assert not _spells('root ::= x\nx ::= x "c" | "d"\n', "x", "\n\n")


# ── last_charset: the exact mirror of first_charset's own stopping rule ───


def test_last_charset_stops_at_the_first_non_nullable_item():
    """Walking backward, the set includes the first non-nullable item's own
    characters and then stops — an item further left never leaks into what
    the arm is proven to end with, exactly as ``first_charset`` never lets
    an item past its own first non-nullable one leak forward."""
    rule_map = _rule_map(
        "root ::= item\nitem ::= lead mid tail\n"
        'lead ::= "Q"\nmid ::= "!"\ntail ::= "z"?\n'
    )
    items = _arm_items(rule_map, "item")
    ending = last_charset(items, rule_map, frozenset())
    assert ending.has("z") and ending.has("!")
    assert not ending.has("Q")
