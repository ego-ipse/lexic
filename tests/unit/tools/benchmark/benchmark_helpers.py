"""Shared fixtures for the benchmark harness tests: one well-formed row."""

from __future__ import annotations

from pathlib import Path

from tools.benchmark.measurement.contract import (
    CLOCKS,
    PROTOCOL,
    Observation,
    RowContract,
)

BASE = Path("/tmp/base")
HEAD = Path("/tmp/head")

CONTRACT = RowContract(
    PROTOCOL,
    "lexic-pda",
    "json",
    "abc123",
    (),
    (),
    "def456",
    2403,
    "corpus",
    "typed model",
    1,
    True,
    CLOCKS,
)
"""A well-formed contract for one sequential row, identical on both arms."""

OBSERVED = Observation(1.0, 1.0, "text", "shape", "accepted", None, "plan", 1, 0, 0.0)
"""A well-formed observation of one accepted sequential row; tests overwrite
the clocks and keep the rest."""
