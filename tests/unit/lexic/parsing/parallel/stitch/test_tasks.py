"""Focused task-routing and ownership guards for model stitching."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.discovery.interiors import interior_rules
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.stitch.safety import owner_excludes


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
