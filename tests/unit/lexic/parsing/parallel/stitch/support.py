"""Shared exact-split fixture for stitch seam tests."""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import CompiledGrammar, compile_text
from lexic.ir import IrAst
from lexic.model import GrammarModel
from lexic.parsing import ModelExecutable, parse_model
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.stitch.plan import RegionPlan, derive_plan


class RecordingParse(NamedTuple):
    """Model parser recording each rooted grammar and source size."""

    calls: list[tuple[str, int]]

    def __call__[M](
        self,
        grammar: IrAst,
        source: str,
        binding: ModelExecutable[M],
        resolve: Resolver | None = None,
    ) -> M:
        """Record one call, then invoke the ordinary model product."""
        self.calls.append((str(grammar.start), len(source)))
        return parse_model(grammar, source, binding, resolve)


def recorded_split(
    compiled: CompiledGrammar, text: str, cores: int
) -> tuple[RecordingParse, GrammarModel | None]:
    """Attempt one split through a recording model product."""
    recording = RecordingParse([])
    parallel = split_model(
        recording,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        cores,
    )
    return recording, parallel


def split_case(
    source: str, text: str, rule: str, cores: int
) -> tuple[RegionPlan | None, GrammarModel, GrammarModel | None]:
    """Return the plan, sequential model, and attempted exact split model."""
    compiled = compile_text(source)
    grammar, binding = compiled.codegen_grammar, compiled.product
    return (
        derive_plan(grammar, binding, rule),
        parse_model(grammar, text, binding),
        split_model(parse_model, grammar, Request(text, binding), cores),
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
