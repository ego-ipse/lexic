"""The watch's cost model, measured: pay to watch, and only then.

Two claims, one experiment each, both in-process and interleaved — a
cross-process comparison against a stored number drifts with machine state and
would decide nothing here.

1. **The unwatched path is untouched.** Measured ALONE first, then again
   interleaved with watched runs of the same document. If the watch had put a
   branch on the hot loop — or if merely having a second kernel subclass around
   poisoned the driver's call sites — the interleaved samples would be slower
   than the solo ones. They are not.
2. **Watching costs something.** The watched run is measurably dearer than the
   unwatched one, which is what makes "pay to watch" a real statement rather
   than a claim that instrumentation is free.

The structural half of claim 1 — that no method of ``PdaKernel`` so much as
names the watch — is gated in ``tests/unit/lexic/parsing/test_trace.py``, where
it is decisive rather than statistical.
"""

from __future__ import annotations

import statistics

import pytest

from lexic.compile import compile_from_path
from lexic.parsing import parse_model, watch
from tests.paths import GROUND_TRUTH

from .conftest import timed

DOCUMENT = '{"alpha": [1, 2, 3], "beta": {"gamma": "delta"}, "epsilon": 42}'

ROUNDS = 60
"""Samples per arm. Enough for a stable median under `-n auto` load without
turning the default suite into a benchmark run."""

SLACK = 2.0
"""How much slower the interleaved unwatched median may be before the claim
counts as broken. Generous on purpose: this catches a branch added to the paid
loop, not scheduler noise."""


@pytest.fixture(name="compiled", scope="module")
def compiled_fixture():
    """The JSON grammar, compiled and warm (tables and memos already built)."""
    grammar = compile_from_path(GROUND_TRUTH / "json.gbnf")
    parse_model(grammar.codegen_grammar, DOCUMENT, grammar.fold)
    watch(grammar.pda_tables(), DOCUMENT, grammar.fold)
    return grammar


def unwatched(compiled) -> float:
    """One unwatched parse, timed."""
    _, seconds = timed(
        lambda: parse_model(compiled.codegen_grammar, DOCUMENT, compiled.fold)
    )
    return seconds


def watched(compiled) -> float:
    """One watched parse, timed."""
    _, seconds = timed(lambda: watch(compiled.pda_tables(), DOCUMENT, compiled.fold))
    return seconds


@pytest.mark.performance
def test_the_unwatched_path_is_untouched_by_the_watch(compiled) -> None:
    """Claim 1: solo and interleaved unwatched medians agree."""
    solo = sorted(unwatched(compiled) for _ in range(ROUNDS))
    mixed = []
    for _ in range(ROUNDS):
        mixed.append(unwatched(compiled))
        watched(compiled)
    solo_median = statistics.median(solo)
    mixed_median = statistics.median(sorted(mixed))
    assert mixed_median <= solo_median * SLACK, (
        f"unwatched parse slowed when watched runs interleave: "
        f"{mixed_median * 1e6:.1f}us vs {solo_median * 1e6:.1f}us solo"
    )


@pytest.mark.performance
def test_watching_costs_more_than_not_watching(compiled) -> None:
    """Claim 2: the instrumentation is real, and it is the watcher who pays."""
    pairs = [(unwatched(compiled), watched(compiled)) for _ in range(ROUNDS)]
    quiet = statistics.median(sorted(a for a, _ in pairs))
    loud = statistics.median(sorted(b for _, b in pairs))
    assert loud > quiet, (
        f"a watched run ({loud * 1e6:.1f}us) was not dearer than an unwatched "
        f"one ({quiet * 1e6:.1f}us) — is the watch recording anything?"
    )
