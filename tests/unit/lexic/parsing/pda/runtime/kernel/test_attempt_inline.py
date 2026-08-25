"""Tests for the attempt-aware frame-less value-string loops."""

from __future__ import annotations

import pytest

from lexic.compile import Directives, compile_text
from lexic.parsing.pda.runtime.kernel.decisions import Attempting
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.trace import watch
from tests.unit.lexic.parsing.pda.compiler.program.test_specialize import (
    ATTEMPT_GATED_VSTR,
)
from tests.unit.lexic.parsing.pda.compiler.test_clones import pda_from_text
from tools.benchmark.cases.grammars import BENCHES


def test_an_attempt_aware_value_str_runs_its_fused_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The specialised item must not return to the per-iteration driver."""

    def unexpected(*_args: object) -> int:
        raise AssertionError("attempt-aware value_str used the generic loop")

    monkeypatch.setattr(Attempting, "attempt_iteration", unexpected)
    model = pda_model(pda_from_text(ATTEMPT_GATED_VSTR), "aaac")
    assert model.to_text() == "aaac"


def test_a_resumed_attempt_probe_keeps_its_completed_iteration() -> None:
    """A take-side probe must not demand its consumed iteration again at EOF."""
    bench = next(candidate for candidate in BENCHES if candidate.name == "gbnf-meta")
    compiled = compile_text(
        bench.source,
        cache_key="attempt-inline-resumed-count",
        flavour=bench.flavour,
        directives=Directives(lexical=frozenset({"comment-line"})),
    )
    chunk = bench.full[2542:5117]
    tables = compiled.pda_tables()

    run = watch(tables, chunk, compiled.fold, cap=10_000)

    assert run.derived
    assert pda_model(tables, chunk, compiled.fold).to_text() == chunk
