"""Root conftest: shared pytest fixtures for the full test suite."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import lexic.compile as compile_pkg
import lexic.grammars as grammars_pkg
from lexic.parsing.parallel import available_workers
from tests.paths import GROUND_TRUTH


@pytest.fixture(scope="session")
def ground_truth() -> Path:
    """Return the ground-truth grammars directory."""
    return GROUND_TRUTH


@pytest.fixture
def registry_snapshot(monkeypatch: pytest.MonkeyPatch):
    """Snapshot/restore the flavour registry + reset the compile cache both ends.

    The compile ``_CACHE`` is flavour-NAME-keyed, so a stale entry could let a
    registered-flavour integration run pass vacuously against an authored-built
    ``CompiledGrammar`` (Fable preflight #1); reset it on setup AND teardown.
    ``monkeypatch`` swaps the private registry for a copy it restores on
    teardown, absorbing the silent overwrite of an authored singleton.
    """
    registry = getattr(grammars_pkg, "_FLAVOURS")
    monkeypatch.setattr(grammars_pkg, "_FLAVOURS", dict(registry))
    compile_pkg.reset_cache_for_tests()
    yield
    compile_pkg.reset_cache_for_tests()


def pytest_configure(config: pytest.Config) -> None:
    """Register the lane marker, and enforce the environment a phase asked for.

    The marker is declared here rather than in ``pyproject.toml`` because that
    file is harness: ``addinivalue_line`` is pytest's own supported route and
    needs no edit to it.

    Both guards FAIL the session rather than skipping. A concurrency phase that
    quietly runs with the GIL on, or on one core, reports green having proven
    nothing — which is the failure mode the whole lane exists to avoid.
    """
    config.addinivalue_line(
        "markers", "concurrency: thread-safety lane; runs serial, never under xdist"
    )
    if os.environ.get("LEXIC_REQUIRE_FREE_THREADED") == "1" and not _free_threaded():
        raise pytest.UsageError(
            "LEXIC_REQUIRE_FREE_THREADED=1 but this interpreter runs WITH "
            f"the GIL ({sys.version.split()[0]}). A free-threaded build is "
            "python3.14t; PYTHON_GIL=1 must not be set for this phase."
        )
    if os.environ.get("LEXIC_REQUIRE_GIL") == "1" and _free_threaded():
        raise pytest.UsageError(
            "LEXIC_REQUIRE_GIL=1 but the GIL is OFF. The weak witness has to "
            "prove it is weak: without this the run silently duplicates the "
            "free-threaded one and the matrix tests a single configuration "
            "twice. Set PYTHON_GIL=1 for this phase."
        )
    want = os.environ.get("LEXIC_REQUIRE_CORES")
    if want and _free_threaded() and available_workers() < int(want):
        raise pytest.UsageError(
            f"LEXIC_REQUIRE_CORES={want} but available_workers() reports "
            f"{available_workers()} on a free-threaded interpreter. Threads "
            "cannot overlap here, so this phase would pass without racing "
            "anything."
        )


def _free_threaded() -> bool:
    """Whether the GIL is off for this run.

    The core floor is asked only here, and that is not a loophole. With the
    GIL off, one usable worker means a genuinely one-core machine and the
    concurrency lane is vacuous — worth failing over. With the GIL ON,
    ``available_workers()`` reports 1 by deliberate engine POLICY (threaded
    parsing under the GIL measured a net loss), so the same reading says
    nothing about the machine. The lane still runs there; it simply runs as
    the acknowledged weak witness, which is why its overlap bar degrades to 1
    rather than pretending to a simultaneity that build cannot offer.
    """
    gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return gil_enabled is not None and not gil_enabled()
