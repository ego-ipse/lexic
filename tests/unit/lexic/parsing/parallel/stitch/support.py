"""Shared exact-split fixture for stitch seam tests."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.model import GrammarModel
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.stitch.model import RegionPlan, derive_plan


def split_case(
    source: str, text: str, rule: str, cores: int
) -> tuple[RegionPlan | None, GrammarModel, GrammarModel | None]:
    """Return the plan, sequential model, and attempted exact split model."""
    compiled = compile_text(source)
    grammar, fold = compiled.codegen_grammar, compiled.fold
    return (
        derive_plan(grammar, fold, rule),
        parse_model(grammar, text, fold),
        split_model(parse_model, grammar, Request(text, fold), cores),
    )


def assert_exact_split(
    result: tuple[RegionPlan | None, GrammarModel, GrammarModel | None],
    text: str,
) -> RegionPlan | None:
    """Assert exact model/text parity and return the derived plan."""
    plan, sequential, parallel = result
    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text
    return plan


def assert_outer_split(
    result: tuple[RegionPlan | None, GrammarModel, GrammarModel | None],
    text: str,
) -> None:
    """Assert exact parity plus configured outer boundary slots."""
    plan = assert_exact_split(result, text)
    assert plan is not None
    assert plan.outer_begin is not None and plan.outer_end is not None
