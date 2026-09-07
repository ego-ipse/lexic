"""Tests for the same-tree execution-health report.

This asks a different question from the A/B: not "is head slower than base" but
"does this tree's AUTO policy pick well among the core counts it was measured
against". A pre-existing parallel loss and a new regression are different facts.
"""

from __future__ import annotations

from tools.benchmark.measurement import health

BYTES = 32768


def _reading(cores: int, wall_ms: float, cpu_ms: float) -> health.Reading:
    """One core count's answer, in the units the report reads."""
    return health.Reading(
        cores, wall_ms / 1e3, cpu_ms / 1e3, cores != 1, max(cores, 1), BYTES
    )


def test_auto_that_beats_every_fixed_count_passes() -> None:
    """A policy that picked the best available answer has earned its threading."""
    readings = [
        _reading(1, 40.0, 40.0),
        _reading(8, 15.0, 70.0),
        _reading(health.AUTO, 14.5, 69.0),
    ]

    assert health.verdict("json", readings) is None


def test_auto_slower_than_one_worker_fails() -> None:
    """Threading that loses outright is a loss, whatever it cost."""
    readings = [_reading(1, 20.0, 20.0), _reading(health.AUTO, 25.0, 90.0)]

    assert "not faster than one worker" in str(health.verdict("json", readings))


def test_auto_that_overshoots_a_better_fixed_count_fails() -> None:
    """Beating ONE worker is not the bar when every count was measured."""
    readings = [
        _reading(1, 40.0, 40.0),
        _reading(8, 14.75, 69.0),
        _reading(16, 15.14, 113.8),
        _reading(health.AUTO, 15.85, 115.8),
    ]
    why = str(health.verdict("nested", readings))

    assert "slower than cores=8" in why
    assert "1.68x its CPU" in why


def test_a_small_cpu_premium_for_a_real_latency_win_is_allowed() -> None:
    """Threading buys latency with CPU; some overhead is the price of the win."""
    readings = [
        _reading(1, 40.0, 40.0),
        _reading(8, 15.0, 70.0),
        _reading(health.AUTO, 15.2, 75.0),
    ]

    assert health.verdict("json", readings) is None


def test_a_grammar_whose_split_declines_is_not_a_failure() -> None:
    """An honest decline is an answer, not a loss to be fixed."""
    readings = [
        _reading(1, 40.0, 40.0),
        health.Reading(health.AUTO, 0.041, 0.041, False, 1, BYTES),
    ]

    assert health.verdict("mixedends", readings) is None
