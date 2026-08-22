"""Focused shell and boundary reconstruction tests."""

# The model and merge counterparts intentionally assert the same public
# equality/round-trip contract at different reconstruction seams.
# pylint: disable=duplicate-code

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.stitch.model import derive_plan

OUTER = (
    "root ::= outer\n"
    "outer ::= lead group trail\n"
    'lead ::= "[" ws\n'
    "group ::= open items close\n"
    'open ::= "{" ws\n'
    'close ::= ws "}"\n'
    "items ::= item more*\n"
    "more ::= comma item\n"
    'comma ::= "," ws\n'
    "item ::= [a-z]+\n"
    'trail ::= ws "]"\n'
    'ws ::= " "*\n'
)


def test_configured_outer_arm_preserves_closing_boundary_spaces() -> None:
    """An indirect group keeps whitespace owned by its closing arm."""
    compiled = compile_text(OUTER)
    text = "[ { " + ", ".join("a" * 20 for _ in range(900))
    text += "   } ]"
    grammar, fold = compiled.codegen_grammar, compiled.fold
    plan = derive_plan(grammar, fold, "group")
    sequential = parse_model(grammar, text, fold)
    parallel = split_model(parse_model, grammar, Request(text, fold), 4)

    assert plan is not None
    assert plan.outer_begin is not None and plan.outer_end is not None
    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text


def test_mixed_separator_whitespace_survives_shallow_joint_reconstruction() -> None:
    """Boundary tails retain varying separator whitespace during a shallow join."""
    compiled = compile_text(OUTER)
    separators = [", ", ",    ", ",   ", ",  "]
    items = ["a" * 20]
    for index in range(899):
        items.append(separators[index % len(separators)] + "a" * 20)
    text = "[ { " + "".join(items) + " } ]"
    grammar, fold = compiled.codegen_grammar, compiled.fold
    sequential = parse_model(grammar, text, fold)
    parallel = split_model(parse_model, grammar, Request(text, fold), 8)

    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text
