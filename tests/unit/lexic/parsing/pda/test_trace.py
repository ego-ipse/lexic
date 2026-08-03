"""The predictive runtime's trace seam — off by default, exact when on."""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.parsing import PdaKernel, Step, Watch
from tests.paths import GROUND_TRUTH

_TOY = 'root ::= "a" body\nbody ::= "b" | "c"\n'


def test_a_parse_records_nothing_by_default() -> None:
    """An untraced parse allocates no steps — the seam is opt-in."""
    compiled = compile_text(_TOY)
    kernel = PdaKernel(compiled.pda_tables(), "ab", compiled.fold)
    kernel.run()
    assert kernel.trace is None


def test_a_traced_parse_records_every_clone_it_enters() -> None:
    """Each clone entered appends one step naming what it builds."""
    compiled = compile_text(_TOY)
    steps: list[Step] = []
    PdaKernel(compiled.pda_tables(), "ab", compiled.fold, Watch(trace=steps)).run()
    assert steps
    assert all(isinstance(step, Step) for step in steps)
    assert {step.kind for step in steps} == {"enter"}
    assert "Root" in {step.name for step in steps}


def test_every_step_sits_within_the_input() -> None:
    """A step's position is a real offset, never past the text."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    text = '{"a":[1,true]}'
    steps: list[Step] = []
    PdaKernel(compiled.pda_tables(), text, compiled.fold, Watch(trace=steps)).run()
    assert steps
    assert all(0 <= step.start <= len(text) for step in steps)
    assert all(step.end >= step.start for step in steps)


def test_the_trace_names_the_build_mode_of_each_clone() -> None:
    """A step says what kind of clone it was, in words rather than a code."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    steps: list[Step] = []
    PdaKernel(compiled.pda_tables(), '{"a":1}', compiled.fold, Watch(trace=steps)).run()
    modes = {step.note for step in steps}
    assert modes <= {
        "transparent",
        "value-str",
        "alternation",
        "sequence",
        "dispatch",
        "reduce",
        "?",
    }
    assert "sequence" in modes


def test_tracing_does_not_change_what_a_parse_produces() -> None:
    """The seam observes; it must not participate."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    text = '{"a":[1,true],"b":null}'
    plain = PdaKernel(compiled.pda_tables(), text, compiled.fold).run()
    steps: list[Step] = []
    traced = PdaKernel(
        compiled.pda_tables(), text, compiled.fold, Watch(trace=steps)
    ).run()
    assert plain == traced
    assert plain.to_text() == traced.to_text() == text


def test_a_refused_parse_still_records_what_it_managed() -> None:
    """A trace of a failure is the useful one — it stops where it stopped."""
    compiled = compile_text(_TOY)
    steps: list[Step] = []
    with pytest.raises(Exception):
        PdaKernel(compiled.pda_tables(), "az", compiled.fold, Watch(trace=steps)).run()
    assert steps
    assert steps[0].name == "Root"
