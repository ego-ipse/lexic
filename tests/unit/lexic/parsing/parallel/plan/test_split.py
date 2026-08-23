"""Tests for lexic.parsing.parallel.plan.split — SplitPlan, the reusable
per-grammar cut shape.

The plans's fields are populated by the shape analyses
(``discovery/``, ``plan/envelope.py``, ``plan/routed.py``) and driven by
``orchestrate.split_plan``, which is where realistic plans are exercised
end to end; this file targets ``SplitPlan.terminated`` directly, over real
plans of both shapes.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel import split_plan

TERMINATED_SOURCE = 'root ::= line+\nline ::= [a-z]+ "\\n"\n'
SEPARATED_SOURCE = (
    'root ::= expr\nexpr ::= number (addop number)*\naddop ::= "+" | "-"\n'
    "number ::= [0-9]+\n"
)


def test_a_terminated_plan_has_no_separator_and_reports_terminated():
    """A ``unit+`` grammar has no separator and terminated is True."""
    compiled = compile_text(TERMINATED_SOURCE, cache_key="split-terminated")
    plan = split_plan(compiled.codegen_grammar)
    assert plan is not None
    assert plan.sep is None
    assert plan.envelope is None
    assert plan.terminated


def test_a_separated_plan_carries_a_separator_and_reports_not_terminated():
    """A ``unit (sep unit)*`` grammar carries a separator and is not terminated."""
    compiled = compile_text(SEPARATED_SOURCE, cache_key="split-separated")
    plan = split_plan(compiled.codegen_grammar)
    assert plan is not None
    assert plan.sep is not None
    assert not plan.terminated


def test_a_terminated_plan_names_the_repeated_unit_as_its_owner():
    """The repeated unit rule is the owner that must exclude the mark."""
    compiled = compile_text(TERMINATED_SOURCE, cache_key="split-terminated-owner")
    plan = split_plan(compiled.codegen_grammar)
    assert plan is not None
    assert plan.owner == "line"


def test_a_non_splittable_grammar_has_no_plan():
    """A plain sequence with no repetition has no split plan at all."""
    compiled = compile_text('root ::= "a" "b" "c"\n', cache_key="split-none")
    assert split_plan(compiled.codegen_grammar) is None
