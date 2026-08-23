"""Focused model-plan tests for direct and configured recurrences."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.model import GrammarModel
from lexic.parsing import parse_model
from lexic.parsing.fold import ModelFold
from lexic.parsing.parallel.plan.envelope import Envelope, envelope_plans, unit_witness
from lexic.parsing.parallel.stitch.model import (
    derive_plan,
    envelope_tails,
    stitch_envelope,
)
from tests.unit.lexic.parsing.parallel.envelope_fixtures import ENVELOPE_SOURCE
from tests.unit.lexic.parsing.parallel.stitch.support import (
    assert_outer_split,
    split_case,
)


def _envelope_case(cache_key: str) -> tuple[IrAst, ModelFold, Envelope, IrAst]:
    """The compiled fixture, its envelope shape, and the reparse target."""
    compiled = compile_text(ENVELOPE_SOURCE, cache_key=cache_key)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    plan = _first(envelope_plans(grammar, "root"))
    assert plan is not None
    target = IrAst(grammar.rules, plan.shape.item)
    return grammar, fold, plan.shape, target


def _rebuilt_lead(
    grammar: IrAst, fold: ModelFold, shape: Envelope, target: IrAst, tail_text: str
) -> GrammarModel:
    """The reparsed separator span a real cut hands to the join — the
    separator itself is empty in every case exercised here, so only the
    piece's own moved tail and the witness feed the reparse."""
    witness = unit_witness(grammar, shape.unit) or ""
    return parse_model(target, tail_text + witness, fold)


def _moved_tails(
    chunks: list[GrammarModel], shape: Envelope, fold: ModelFold
) -> tuple[list[str], list[GrammarModel]]:
    """Non-``None`` :func:`envelope_tails`, for callers that already expect it
    to succeed over this fixture's shape."""
    moved = envelope_tails(chunks, shape, fold)
    assert moved is not None
    return moved


def _first(found):
    """The first certified plan, or ``None`` — the shape these tests pin.

    ``envelope_plans`` returns one plan per PROVABLE mark so the
    orchestrator can pick per document; a test naming one grammar wants
    the leading candidate.
    """
    return found[0] if found else None


def test_a_trailing_comment_absorbed_by_a_pieces_own_tail_reparses_and_stitches() -> (
    None
):
    """A piece ending ``rule ; note\\n`` keeps that comment as its OWN tail
    field when parsed alone; :func:`envelope_tails` moves it back out to text,
    and the reparsed separator, joined with the next piece's real head,
    equals the document parsed whole — byte for byte."""
    grammar, fold, shape, target = _envelope_case("test-model-envelope-comment")
    whole = "ua = a; note\nub = b"
    piece1 = parse_model(grammar, "ua = a; note\n", fold)
    piece2 = parse_model(grammar, "ub = b", fold)

    texts, trimmed = _moved_tails([piece1, piece2], shape, fold)
    assert texts == ["; note\n"]

    lead = _rebuilt_lead(grammar, fold, shape, target, texts[0])
    stitched = stitch_envelope(trimmed, [lead], shape, fold)

    assert stitched is not None
    assert stitched == parse_model(grammar, whole, fold)
    assert stitched.to_text() == whole


def test_a_moved_bare_newline_supplies_the_next_items_required_line_ending() -> None:
    """A piece ending with nothing but its own trailing blank line still
    moves that ``\\n`` to the separator, which is what lets ``cont``'s
    mandatory ``cnl`` item resolve once the witness is appended."""
    grammar, fold, shape, target = _envelope_case("test-model-envelope-blank")
    whole = "ua = a\nub = b"
    piece1 = parse_model(grammar, "ua = a\n", fold)
    piece2 = parse_model(grammar, "ub = b", fold)

    texts, trimmed = _moved_tails([piece1, piece2], shape, fold)
    assert texts == ["\n"]

    lead = _rebuilt_lead(grammar, fold, shape, target, texts[0])
    stitched = stitch_envelope(trimmed, [lead], shape, fold)

    assert stitched is not None
    assert stitched == parse_model(grammar, whole, fold)
    assert stitched.to_text() == whole


def test_a_non_final_piece_carrying_a_head_field_declines_the_envelope_stitch() -> None:
    """The head belongs to the document's opening edge alone: a later piece
    that parsed one when read independently has read a boundary differently
    than the split did, and the stitch must refuse rather than silently keep
    only the first piece's head."""
    grammar, fold, shape, target = _envelope_case("test-model-envelope-head")
    piece1 = parse_model(grammar, "ua = a\n", fold)
    piece2 = parse_model(grammar, "; lead\nub = b", fold)

    texts, trimmed = _moved_tails([piece1, piece2], shape, fold)
    lead = _rebuilt_lead(grammar, fold, shape, target, texts[0])

    assert stitch_envelope(trimmed, [lead], shape, fold) is None


def test_direct_candidate_short_tail_arm_declines_without_index_error() -> None:
    """A malformed direct tail is a safe decline, not an indexing fallback."""
    compiled = compile_text(
        'root ::= group\ngroup ::= "(" node more* ")"\nnode ::= [a-z]+\nmore ::= ","\n'
    )

    assert derive_plan(compiled.codegen_grammar, compiled.fold, "group") is None
    assert compiled.parse("(alpha)").to_text() == "(alpha)"


def test_direct_trailing_boundary_whitespace_round_trips_after_split() -> None:
    """Direct recurrence reconstruction retains whitespace before its closer."""
    source = (
        "root ::= group\n"
        "group ::= open node more* close\n"
        'open ::= "(" ws\n'
        'close ::= ws ")"\n'
        'more ::= "," node\n'
        "node ::= [a-z]+\n"
        'ws ::= " "*\n'
    )

    text = "(" + ",".join("a" * 20 for _ in range(900)) + "   )"
    assert_outer_split(split_case(source, text, "group", 4), text)
