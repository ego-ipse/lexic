"""Focused task-routing and ownership guards for model stitching."""

from __future__ import annotations

from lexic.compile import compile_ast, compile_text
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.discovery.interiors import interior_rules
from lexic.parsing.parallel.discovery.regions import choose, find, piece_marks
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.stitch.merge import MergeRequest
from lexic.parsing.parallel.stitch.safety import owner_excludes
from lexic.parsing.parallel.stitch.tasks import region_works
from tests.unit.lexic.parsing.parallel.stitch.support import record_stitches


def test_true_start_rule_is_filtered_before_piece_parsing() -> None:
    """A region rooted at the document start has no shell route."""
    compiled = compile_text(
        'group ::= "(" node ("," node)* ")"\nnode ::= leaf | group\nleaf ::= [a-z]+\n'
    )
    text = "(" + ",".join("a" * 20 for _ in range(900)) + ")"
    calls: list[str] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append(source)
        return parse_model(grammar, source, fold, resolve)

    grammar, binding = compiled.codegen_grammar, compiled.product
    assert split_model(recording_parse, grammar, Request(text, binding), 4) is None
    assert not calls
    assert compiled.parse(text, cores=1).to_text() == text


def test_quote_like_rule_not_classified_as_interior_does_not_protect_owner() -> None:
    """Only discovered interiors may hide separator emissions from an owner.

    The shape alone does not discover one: a delimiter another reachable rule
    also spells cannot be paired from the left, so the region stays read.
    """
    compiled = compile_text(
        "root ::= item more*\n"
        'more ::= "," item\n'
        "item ::= quote | mark\n"
        'quote ::= "\\"" comma "\\""\n'
        'mark ::= "\\""\n'
        'comma ::= ","\n'
    )
    grammar = compiled.grammar

    assert "quote" not in interior_rules(grammar)
    assert not owner_excludes(grammar, "item", ",")


UNEVEN = [9000, 2500, 2500, 9000, 5000, 2500, 300, 900, 40, 40]
"""Item sizes whose 8-way target positions share a nearest separator: the
region divides into 5 pieces, and asked again for 5 it would cut only 3."""


def _uneven() -> str:
    """A json array of :data:`UNEVEN` strings, no whitespace."""
    return "[" + ",".join('"' + "q" * k + '"' for k in UNEVEN) + "]"


def test_a_work_binds_the_cuts_its_pieces_were_cut_at() -> None:
    """Not a re-derivation: at the pieces' own count it would come out shorter."""
    compiled = compile_ast(JSON_GRAMMAR)
    grammar, text = compiled.codegen_grammar, _uneven()
    divided = choose(text, find(grammar, text), 8)
    (division,) = divided
    assert len(piece_marks(division.region, len(division.parts))) != len(division.cuts)
    request = MergeRequest(parse_model, text, compiled.product, None)
    works = region_works(request, grammar, divided, grammar) or []
    assert [work.cuts for work in works] == [division.cuts]


def test_a_division_whose_cuts_would_rederive_differently_still_stitches(
    monkeypatch,
) -> None:
    """The split is taken — not declined into a sequential parse — and its
    model is the sequential one."""
    compiled = compile_ast(JSON_GRAMMAR)
    text = _uneven()
    stitched = record_stitches(monkeypatch)
    split = compiled.parse(text, cores=8)
    assert stitched == [True]
    assert split.dump() == compiled.parse(text, cores=1).dump()
