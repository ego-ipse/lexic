"""Tests for ``lexic.parsing.parallel.policy`` — the worker-count policy.

Auto mode gates on the free-threaded build (a GIL build LOSES from
splitting), then clamps by cpus, chunk floor and split supply. An explicit
override is a decision: only the structural bound applies.
"""

from __future__ import annotations

import os

import pytest

from lexic.parsing.parallel import MIN_CHUNK, doc_workers
from lexic.parsing.parallel import policy as policy_module
from lexic.parsing.parallel import worker_count


def test_explicit_override_is_respected():
    """The caller's number is used as given."""
    assert worker_count(10 * MIN_CHUNK, splits=100, cores=4) == 4


def test_explicit_override_clamps_to_the_structural_bound():
    """More workers than chunks is meaningless — splits + 1 caps it."""
    assert worker_count(10 * MIN_CHUNK, splits=2, cores=16) == 3
    assert worker_count(10 * MIN_CHUNK, splits=100, cores=0) == 1


def test_auto_is_sequential_on_a_gil_build(monkeypatch: pytest.MonkeyPatch):
    """No free threading → splitting measured as a net loss → one worker."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: False)
    assert worker_count(100 * MIN_CHUNK, splits=100) == 1


def test_auto_clamps_by_cpus_size_and_splits(monkeypatch: pytest.MonkeyPatch):
    """Free-threaded auto: min(cpus, size // MIN_CHUNK, splits + 1)."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: True)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 8)
    assert worker_count(100 * MIN_CHUNK, splits=100) == 8
    assert worker_count(3 * MIN_CHUNK, splits=100) == 3
    assert worker_count(100 * MIN_CHUNK, splits=1) == 2


def test_auto_never_drops_below_one_worker(monkeypatch: pytest.MonkeyPatch):
    """A tiny document still gets its sequential parse."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: True)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 8)
    assert worker_count(MIN_CHUNK // 2, splits=100) == 1


def test_doc_workers_has_no_chunk_floor(monkeypatch: pytest.MonkeyPatch):
    """Document-level auto is gated by the build and cpus, never by size."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: True)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 8)
    assert doc_workers() == 8
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: False)
    assert doc_workers() == 1
    assert doc_workers(cores=4) == 4
    assert doc_workers(cores=0) == 1
