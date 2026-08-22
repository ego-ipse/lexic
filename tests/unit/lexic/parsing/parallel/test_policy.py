"""Tests for ``lexic.parsing.parallel.policy`` — what ``cores`` means.

One reading everywhere: 0 (the default) is as many workers as the machine
and the work allow, 1 is sequential, N is that many. An explicit number is
a decision, so the build/size heuristics do not second-guess it — only the
bounds that would make a worker meaningless still apply.
"""

from __future__ import annotations

import os

import pytest

from lexic.parsing.parallel import AUTO, MIN_CHUNK, available_workers, doc_workers
from lexic.parsing.parallel import policy as policy_module
from lexic.parsing.parallel import worker_count


@pytest.fixture(name="eight_cores")
def _eight_cores(monkeypatch: pytest.MonkeyPatch) -> None:
    """A free-threaded machine with eight cpus."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: True)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 8)


def test_auto_is_one_under_the_gil(monkeypatch: pytest.MonkeyPatch):
    """Threaded parsing measured a net loss under the GIL — auto declines."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: False)
    assert available_workers() == 1
    assert doc_workers(AUTO) == 1
    assert worker_count(100 * MIN_CHUNK, splits=100, cores=AUTO) == 1


@pytest.mark.usefixtures("eight_cores")
def test_auto_is_the_cpu_count_when_free_threaded():
    """As many as the machine allows — that is what 0 asks for."""
    assert available_workers() == 8
    assert doc_workers(AUTO) == 8
    assert worker_count(100 * MIN_CHUNK, splits=100, cores=AUTO) == 8


@pytest.mark.usefixtures("eight_cores")
def test_one_core_is_the_way_to_say_sequential():
    """``cores=1`` is explicit, and nothing overrides it upward."""
    assert doc_workers(1) == 1
    assert worker_count(100 * MIN_CHUNK, splits=100, cores=1) == 1


def test_an_explicit_count_is_a_ceiling_with_a_chunk_floor(
    monkeypatch: pytest.MonkeyPatch,
):
    """An explicit N is honored once each requested chunk clears the floor."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: False)
    assert doc_workers(4) == 4
    assert worker_count(1000 * MIN_CHUNK, splits=100, cores=4) == 4
    assert worker_count(1000, splits=100, cores=4) == 1


@pytest.mark.usefixtures("eight_cores")
def test_workers_never_exceed_the_chunks_they_would_parse():
    """Two chunks cannot occupy eight workers, however many were asked for."""
    assert worker_count(100 * MIN_CHUNK, splits=1, cores=8) == 2
    assert worker_count(100 * MIN_CHUNK, splits=1, cores=AUTO) == 2


@pytest.mark.usefixtures("eight_cores")
def test_auto_also_respects_the_chunk_floor():
    """Below the floor per worker, splitting costs more than it saves."""
    assert worker_count(3 * MIN_CHUNK, splits=100, cores=AUTO) == 3
    assert worker_count(MIN_CHUNK // 2, splits=100, cores=AUTO) == 1


@pytest.mark.usefixtures("eight_cores")
def test_a_zero_or_negative_explicit_count_still_parses():
    """Never fewer than one worker — someone has to do the parse."""
    assert doc_workers(-1) == 1
    assert worker_count(100 * MIN_CHUNK, splits=100, cores=-1) == 1
