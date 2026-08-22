"""Focused model-plan tests for direct and configured recurrences."""

# The model and merge counterparts intentionally assert the same public
# equality/round-trip contract at different reconstruction seams.
# pylint: disable=duplicate-code

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.stitch.model import derive_plan


def test_direct_candidate_short_tail_arm_declines_without_index_error() -> None:
    """A malformed direct tail is a safe decline, not an indexing fallback."""
    compiled = compile_text(
        'root ::= group\ngroup ::= "(" node more* ")"\nnode ::= [a-z]+\nmore ::= ","\n'
    )

    assert derive_plan(compiled.codegen_grammar, compiled.fold, "group") is None
    assert compiled.parse("(alpha)").to_text() == "(alpha)"


def test_direct_trailing_boundary_whitespace_round_trips_after_split() -> None:
    """Direct recurrence reconstruction retains whitespace before its closer."""
    compiled = compile_text(
        "root ::= group\n"
        "group ::= open node more* close\n"
        'open ::= "(" ws\n'
        'close ::= ws ")"\n'
        'more ::= "," node\n'
        "node ::= [a-z]+\n"
        'ws ::= " "*\n'
    )
    text = "(" + ",".join("a" * 20 for _ in range(900)) + "   )"
    grammar, fold = compiled.codegen_grammar, compiled.fold
    plan = derive_plan(grammar, fold, "group")
    sequential = parse_model(grammar, text, fold)
    parallel = split_model(parse_model, grammar, Request(text, fold), 4)

    assert plan is not None
    assert plan.outer_begin is not None and plan.outer_end is not None
    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text
