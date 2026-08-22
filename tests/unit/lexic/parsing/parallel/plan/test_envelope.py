"""Tests for ``lexic.parsing.parallel.plan.envelope`` — envelope containers and cuts.

A repetition is not always the bare ``unit item*`` shape ``orchestrate`` plans
over: a container may wrap it in optional head/tail items, and the separator
may be a noise RUN (whitespace, blank lines, comments) rather than one mark
character. These tests exercise the shape reader and the cut derivation
directly, over small authored grammars.
"""

from __future__ import annotations

from lexic.compile import compile_text, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAst, IrRule
from lexic.parsing.parallel.plan.envelope import (
    admits,
    cut_offsets,
    envelope_of,
    envelope_plan,
    extend,
)
from tests.unit.lexic.parsing.parallel.envelope_fixtures import ENVELOPE_SOURCE


def _rules(source: str) -> dict[str, IrRule]:
    ast: IrAst = parse_grammar(source, GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in ast.rules}


def _envelope_grammar() -> IrAst:
    return compile_text(ENVELOPE_SOURCE, cache_key="test-envelope-plan").codegen_grammar


# ── envelope_of: reading a container arm ─────────────────────────────────


def test_envelope_of_reads_the_head_and_tail_items_around_the_core() -> None:
    """The real fixture's ``filler? rule cont* filler?`` arm reads as head/tail
    around the ``rule``/``cont`` core, exactly the abnf-meta diagnosis."""
    rules = _rules(ENVELOPE_SOURCE)
    envelope = envelope_of(rules["root"], rules, "cont")

    assert envelope is not None
    assert envelope.container == "root"
    assert envelope.unit == "rule"
    assert envelope.item == "cont"
    assert envelope.core == 1
    assert envelope.head == (0,)
    assert envelope.tail == (3,)
    assert not envelope.plain


def test_an_arm_with_a_mandatory_head_item_is_not_an_envelope() -> None:
    """A head item that cannot vanish is not owned by one end of a split, so
    the arm declines rather than being read as an envelope."""
    rules = _rules(
        'root ::= head core item*\nhead ::= "H"\ncore ::= "C"\nitem ::= "I"\n'
    )

    assert envelope_of(rules["root"], rules, "item") is None


def test_an_arm_with_a_mandatory_tail_item_is_not_an_envelope() -> None:
    """The same question asked at the other end: a mandatory tail item also
    declines the envelope reading."""
    rules = _rules(
        'root ::= core item* tail\ncore ::= "C"\nitem ::= "I"\ntail ::= "T"\n'
    )

    assert envelope_of(rules["root"], rules, "item") is None


def test_the_plain_unit_item_star_shape_reports_plain() -> None:
    """No head, no tail: the bare shape ``orchestrate`` already serves."""
    rules = _rules('root ::= core item*\ncore ::= "C"\nitem ::= "I"\n')
    envelope = envelope_of(rules["root"], rules, "item")

    assert envelope is not None
    assert envelope.head == ()
    assert envelope.tail == ()
    assert envelope.plain


# ── cut_offsets: normalization and an exact corpus count ────────────────


def test_consecutive_marks_separated_only_by_noise_collapse_to_one_cut() -> None:
    """A unit's own boundary mark immediately followed by a blank line's own
    mark both land on the SAME next unit start; only the earliest is kept."""
    grammar = _envelope_grammar()
    plan = envelope_plan(grammar, "root")
    assert plan is not None
    text = "ua = a\n\nub = b"

    assert plan.cuts(text) == [6]


def test_a_corpus_with_units_a_continuation_and_a_blank_run_yields_exact_counts() -> (
    None
):
    """Three units (``ua``, ``ub``, ``uc``), one of ``ub``'s value spanning a
    continuation line, and a blank line before ``ub``: the two blank-run marks
    at offsets 6 and 7 both individually admit at the same landing spot (only
    the earlier is kept as a cut), and the continuation mark at offset 14 is
    the sole refusal — the exact population this corpus was built to pin."""
    grammar = _envelope_grammar()
    plan = envelope_plan(grammar, "root")
    assert plan is not None
    text = "ua = a\n\nub = b\ncontinuedvalue\nuc = c"

    marks = []
    at = text.find("\n")
    while at != -1:
        marks.append(at)
        at = text.find("\n", at + 1)
    assert marks == [6, 7, 14, 29]

    admitted = [
        admits(text, extend(text, at + 1, plan.run), plan.bound, plan.mark)
        for at in marks
    ]
    assert admitted == [True, True, False, True]
    assert cut_offsets(text, plan.mark, plan.run, plan.bound) == [6, 29]
    assert plan.cuts(text) == [6, 29]
