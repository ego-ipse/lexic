"""Tests for ``lexic.parsing.parallel.plan.routed`` — route-derived interiors.

A grammar shaped ``start ::= head* envelope interior? tail?`` opens its
interior with a mark that is otherwise ubiquitous in the document (a
newline), so no character sweep can find it. The route derivation reads the
start rule's own shape instead: an optional item names a two-armed rule whose
chosen arm is a delimited repetition, and five proofs — arm disjointness, a
head that cannot itself reach the mark, a tail that can vanish, a unit that
terminates exactly once, and the optional item existing at all — gate whether
that reading is safe. Each is exercised independently below by mutating the
one grammar fragment that condition depends on.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.grammars import ABNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel.plan.routed import (
    _optional_ref,
    divide,
    locate,
    routed_plan,
    rule_emits_item,
    terminates_once_ref,
)
from lexic.parsing.parallel.policy import MIN_CHUNK
from tests.unit.lexic.parsing.parallel.routed_fixtures import (
    ROUTED_GRAMMAR,
    routed_document,
    routed_pieces,
)

MARKDOWN_GRAMMAR = 'root ::= fence+\nfence ::= [a-z]+ "\\n"\n'
"""A mandatory unbounded repetition — the start arm's only item is never
optional, so no candidate is ever proposed."""


def _grammar(source: str):
    return compile_text(source).codegen_grammar


# ── derivation: a valid route ────────────────────────────────────────────


def test_a_valid_route_derives_the_interior_rule_opening_closing_and_mark():
    """The generic shape names ``block`` through ``body``'s own alternative,
    opens and marks on ``\\n``, and closes on ``>``."""
    plan = routed_plan(_grammar(ROUTED_GRAMMAR))

    assert plan is not None
    assert plan.rule == "block"
    assert plan.item == "block-item"
    assert plan.opening == "\n"
    assert plan.closing == ">"
    assert plan.mark == "\n"
    assert plan.lead.has("H")
    assert not plan.lead.has("!")
    assert plan.tail.has("\n")
    assert plan.rooted.start == "block"


# ── the five proofs, each declined independently ─────────────────────────


def test_arms_not_first_char_disjoint_decline():
    """Both ``inline`` and ``block`` open with ``\\n``: the arm choice is a
    guess, and a guess declines."""
    source = ROUTED_GRAMMAR.replace(
        'inline ::= " " item (" " item)* " " ">"\n',
        'inline ::= "\\n" item (" " item)* " " ">"\n',
    )
    assert routed_plan(_grammar(source)) is None


def test_a_head_that_can_itself_emit_the_mark_declines():
    """``envelope`` gains the ability to spell ``\\n`` internally, so the
    head-lead proof can no longer tell head lines from the interior."""
    source = ROUTED_GRAMMAR.replace(
        'envelope ::= "!" [A-Z]\n', 'envelope ::= "!" [A-Z\\n]\n'
    )
    assert routed_plan(_grammar(source)) is None


def test_a_tail_item_that_cannot_vanish_declines():
    """The trailing ``\\n`` loses its ``?``: it can no longer vanish, so
    nothing certifies what may stand after the closer."""
    source = ROUTED_GRAMMAR.replace(
        'start ::= head* envelope body? "\\n"?\n',
        'start ::= head* envelope body? "\\n"\n',
    )
    assert routed_plan(_grammar(source)) is None


def test_an_interior_unit_that_fails_terminates_once_declines():
    """``block-item`` gains an arm with no trailing ``\\n`` at all, so not
    every derivation ends at the mark exactly once."""
    source = ROUTED_GRAMMAR.replace(
        'block-item ::= line "\\n"\n', 'block-item ::= line "\\n" | line\n'
    )
    assert routed_plan(_grammar(source)) is None


def test_no_delimited_optional_item_declines():
    """``body`` becomes mandatory: no item in the start arm is a bare
    optional rule reference, so no candidate is ever proposed."""
    source = ROUTED_GRAMMAR.replace(
        'start ::= head* envelope body? "\\n"?\n',
        'start ::= head* envelope body "\\n"?\n',
    )
    assert routed_plan(_grammar(source)) is None


# ── locate: where the interior stands ─────────────────────────────────────


def test_locate_opens_at_the_first_mark_past_multiple_head_lines():
    """Three head lines are walked off before the envelope; the interior's
    opener is pinned to the newline right after the envelope, not the first
    newline in the document."""
    grammar = _grammar(ROUTED_GRAMMAR)
    plan = routed_plan(grammar)
    assert plan is not None
    text = "Hone\nHtwo\nHthree\n!A\nabc\ndef\n>"

    region = locate(text, plan)

    assert region is not None
    assert region.opener == text.index("!A") + 2
    assert text[region.opener] == plan.opening
    assert text[region.closer] == plan.closing


def test_locate_declines_when_the_tail_charset_is_not_matched():
    """Whatever stands after the closer must derive from the start rule's
    own tail; an extra character there is not in the allowed charset."""
    grammar = _grammar(ROUTED_GRAMMAR)
    plan = routed_plan(grammar)
    assert plan is not None
    text = routed_document(20) + "X"

    assert locate(text, plan) is None


def test_locate_finds_an_empty_interior_and_divide_declines_it():
    """Zero marks inside the delimiters is a legitimate region — the block
    body has no lines — but ``divide`` has nothing to cut on and declines."""
    grammar = _grammar(ROUTED_GRAMMAR)
    plan = routed_plan(grammar)
    assert plan is not None
    text = "Hhead\n!A\n>"

    region = locate(text, plan)

    assert region is not None
    assert region.marks == ()
    assert divide(text, region, 4) is None


# ── divide: exact pieces ───────────────────────────────────────────────────


def test_divide_cuts_after_terminators_and_wears_the_regions_delimiters():
    """Every piece opens with the region's own opening character, closes
    with its closing character, and the cut lands right after a unit's own
    terminator — never mid-unit. The document is sized so four pieces clear
    the per-piece floor the division enforces."""
    text = routed_document(1300)
    found = routed_pieces(_grammar(ROUTED_GRAMMAR), text, 4)

    assert found is not None
    plan, _region, parts = found
    assert len(parts) == 4
    for part in parts:
        assert part[0] == plan.opening
        assert part[-1] == plan.closing
        assert part[-2] == plan.mark  # the cut landed after a terminator


# ── regression: unrelated shapes derive no route ───────────────────────────


def test_the_native_json_grammar_derives_no_route():
    """``ws value ws`` has no optional single-rule-reference item at all, so
    the derivation never proposes a candidate — a structurally different
    reason than an arm-disjointness or head-lead failure."""
    rules = {str(rule.name): rule for rule in JSON_GRAMMAR.rules}
    start = rules[str(JSON_GRAMMAR.start)]
    items = tuple(tuple(start.body)[0])

    assert routed_plan(JSON_GRAMMAR) is None
    assert all(_optional_ref(item) is None for item in items)


def test_a_markdown_shaped_mandatory_repetition_derives_no_route():
    """``fence+`` is mandatory and unbounded, never optional — the same
    "no candidate" reason as json, over a completely different shape."""
    grammar = _grammar(MARKDOWN_GRAMMAR)
    rules = {str(rule.name): rule for rule in grammar.rules}
    start = rules[str(grammar.start)]
    items = tuple(tuple(start.body)[0])

    assert routed_plan(grammar) is None
    assert all(_optional_ref(item) is None for item in items)


def test_the_real_abnf_self_grammar_derives_no_route():
    """``rulelist``'s optional ``c-nl`` DOES name a delimited, forced
    ``comment`` arm — a genuine candidate, unlike json or markdown — but the
    mandatory ``rule`` item ahead of it can itself emit a newline, so the
    head-lead proof declines it: a distinct reason from either grammar above."""
    grammar = ABNF_FLAVOUR.grammar
    rules = {str(rule.name): rule for rule in grammar.rules}
    start = rules[str(grammar.start)]
    items = tuple(tuple(start.body)[0])
    candidate = next(item for item in items if _optional_ref(item) == "c-nl")
    emitting = next(item for item in items if str(item.atom) == "rule")

    assert routed_plan(grammar) is None
    assert candidate is not None
    assert rule_emits_item(emitting, "\n", rules)


# ── review fixes: the piece floor, and multi-arm head units ────────────────


def test_divide_caps_workers_at_the_per_piece_floor():
    """The user-pinned 2 KiB floor applies to ACTUAL pieces: a small interior
    at a high worker count divides into fewer, floor-clearing pieces — and an
    interior below two chunks declines outright rather than paying sub-floor
    parses."""
    grammar = _grammar(ROUTED_GRAMMAR)
    small = routed_document(700)  # interior ~4.9 KiB: capacity is two
    found = routed_pieces(grammar, small, 16)
    assert found is not None
    _plan, _region, parts = found
    assert len(parts) == 2
    assert min(len(part) for part in parts) >= MIN_CHUNK

    tiny = routed_document(200)  # interior ~1.4 KiB: below two chunks
    plan = routed_plan(grammar)
    assert plan is not None
    region = locate(tiny, plan)
    assert region is not None
    assert divide(tiny, region, 16) is None


def test_a_multi_arm_head_unit_not_ending_at_the_mark_declines():
    """The locator walks head units off a line at a time, so EVERY head arm
    must end at the mark — a second arm ending elsewhere would carry the walk
    past its own end, and the route declines instead."""
    two_armed = ROUTED_GRAMMAR.replace(
        'head ::= "H" [a-z]* "\\n"\n',
        'head ::= "H" [a-z]* "\\n" | "H" [0-9]+\n',
    )
    grammar = _grammar(two_armed)
    rules = {str(rule.name): rule for rule in grammar.rules}

    assert not terminates_once_ref("head", "\n", rules)
    assert routed_plan(grammar) is None
