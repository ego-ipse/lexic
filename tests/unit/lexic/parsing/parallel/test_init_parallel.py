"""Tests for the ``lexic.parsing.parallel`` façade — the orchestrator's home."""

from __future__ import annotations

import lexic.parsing
from lexic.parsing import parallel


def test_the_facade_exports_the_parallel_vocabulary():
    """Every name in ``__all__`` resolves on the package."""
    for name in parallel.__all__:
        assert getattr(parallel, name) is not None


def test_the_parsing_root_does_not_reexport_the_parallel_layer():
    """Neither engine consumes these names — they stay off the root."""
    assert "anchors" not in lexic.parsing.__all__
    assert "worker_count" not in lexic.parsing.__all__
