"""Focused model-plan tests for direct and configured recurrences."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel.stitch.model import derive_plan
from tests.unit.lexic.parsing.parallel.stitch.support import (
    assert_outer_split,
    split_case,
)


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
