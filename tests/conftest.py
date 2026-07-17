"""Root conftest: shared pytest fixtures for the full test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

import lexic.compile as compile_pkg
import lexic.grammars as grammars_pkg
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
