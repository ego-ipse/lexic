"""Tests for ``lexic.parsing.parallel.pool`` — the document pool.

The pool changes WHEN documents parse, never what a parse means: results
equal the sequential parses, in input order, and a failing document raises
its own exception.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, Thread
from time import sleep

import pytest

import lexic.parsing.parallel.pool as pool_module
from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.parallel import ParsePool
from lexic.parsing.parallel import policy as policy_module
from lexic.parsing.parallel.pool import WorkPool

GRAMMAR = 'root ::= "(" [a-z]+ ")"\n'


class _PhaseState:
    """Events and work behavior for the failed-phase lifecycle test."""

    def __init__(self) -> None:
        """Create synchronization points and captured phase errors."""
        self.events = {
            name: Event()
            for name in (
                "running_started",
                "failure_raised",
                "wait_entered",
                "release_running",
                "running_finished",
                "queued_started",
                "release_queued",
                "queued_finished",
                "canceled_started",
            )
        }
        self.errors: list[BaseException] = []

    def event(self, name: str) -> Event:
        """Return one named synchronization event."""
        return self.events[name]

    def work(self, item: str) -> str:
        """Run one phase item, blocking siblings at deterministic points."""
        if item == "running":
            self.events["running_started"].set()
            self.events["release_running"].wait(5)
            self.events["running_finished"].set()
        elif item == "fail":
            assert self.events["running_started"].wait(5)
            self.events["failure_raised"].set()
            raise ValueError("phase failure")
        elif item == "queued":
            self.events["queued_started"].set()
            self.events["release_queued"].wait(5)
            self.events["queued_finished"].set()
        else:
            self.events["canceled_started"].set()
        return item


class _AdmissionExecutor:
    """Executor seam recording the bounded number of unfinished futures."""

    instances: list[_AdmissionExecutor] = []

    def __init__(self, max_workers: int) -> None:
        """Create a real executor and expose admission counters."""
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.outstanding = 0
        self.maximum = 0
        self.submitted = 0
        self.window_reached = Event()
        self.allow_more = Event()
        self._lock = Lock()
        self.instances.append(self)

    def submit(self, work, *args, **kwargs):
        """Track a future before delegating to the real executor."""
        with self._lock:
            self.outstanding += 1
            self.maximum = max(self.maximum, self.outstanding)
            self.submitted += 1
            if self.submitted == 8:
                self.window_reached.set()
        if self.submitted == 8:
            assert self.allow_more.wait(5)
        future = self.executor.submit(work, *args, **kwargs)
        future.add_done_callback(self._completed)
        return future

    def _completed(self, _future) -> None:
        """Decrement the unfinished-future count after completion."""
        with self._lock:
            self.outstanding -= 1

    def shutdown(self, *args, **kwargs):
        """Delegate executor shutdown."""
        return self.executor.shutdown(*args, **kwargs)


def test_map_equals_sequential_in_input_order():
    """Every model matches its own sequential parse, order preserved."""
    compiled = compile_text(GRAMMAR)
    texts = [f"({'x' * (i + 1)})" for i in range(8)]
    pool = ParsePool(compiled.parse, cores=4)
    models = pool.map(texts)
    pool.close()
    assert models == [compiled.parse(text) for text in texts]
    assert [model.to_text() for model in models] == texts


def test_context_manager_maps_in_order_and_closes_the_pool():
    """A ParsePool context owns shutdown while preserving map ordering."""

    def double(value: int) -> int:
        """Double one integer work item."""
        return value * 2

    pool = ParsePool(double, cores=2)
    with pool:
        assert pool.map([3, 1, 2, 0]) == [6, 2, 4, 0]

    with pytest.raises(RuntimeError, match="cannot schedule new futures"):
        pool.map([4])


def test_work_pool_eagerly_schedules_beyond_the_first_worker_width():
    """A fast later item starts while one early worker remains blocked."""
    first_started = Event()
    later_started = Event()
    release = Event()
    result: list[int] = []

    def work(item: int) -> int:
        if item == 0:
            first_started.set()
            release.wait(5)
        elif item == 2:
            later_started.set()
        return item

    with WorkPool(2) as pool:
        thread = Thread(target=lambda: result.extend(pool.map(work, range(4))))
        thread.start()
        assert first_started.wait(5)
        assert later_started.wait(5)
        release.set()
        thread.join(5)

    assert not thread.is_alive()
    assert result == [0, 1, 2, 3]


def test_failed_phase_cancels_pending_and_waits_running_siblings(
    monkeypatch: pytest.MonkeyPatch,
):
    """A failed map drains siblings before the next phase can begin."""
    state = _PhaseState()

    real_wait = pool_module.wait

    def observed_wait(futures, *args, **kwargs):
        if not args and not kwargs:
            state.events["wait_entered"].set()
        return real_wait(futures, *args, **kwargs)

    monkeypatch.setattr(pool_module, "wait", observed_wait)
    with WorkPool(2) as pool:

        def failed_phase() -> None:
            try:
                pool.map(
                    state.work,
                    ["fail", "running", "queued", "canceled"],
                )
            except ValueError as error:
                state.errors.append(error)

        thread = Thread(target=failed_phase)
        thread.start()
        assert state.events["running_started"].wait(5)
        assert state.events["failure_raised"].wait(5)
        assert state.events["wait_entered"].wait(5)
        assert not state.events["canceled_started"].is_set()
        state.events["release_running"].set()
        state.events["release_queued"].set()
        thread.join(5)

        assert not thread.is_alive()
        assert state.events["running_finished"].is_set()
        assert (
            not state.events["queued_started"].is_set()
            or state.events["queued_finished"].is_set()
        )
        assert state.errors and str(state.errors[0]) == "phase failure"
        assert pool.map(lambda item: item, ["next"]) == ["next"]
        assert not state.events["canceled_started"].is_set()


def test_sliding_admission_bounds_futures_and_starts_beyond_worker_width(
    monkeypatch: pytest.MonkeyPatch,
):
    """Admission stays bounded while a later item starts past worker width."""
    _AdmissionExecutor.instances.clear()
    later_started = Event()
    release = Event()
    results: list[int] = []

    def work(item: int) -> int:
        if item == 2:
            later_started.set()
        assert release.wait(5)
        return item

    monkeypatch.setattr(pool_module, "ThreadPoolExecutor", _AdmissionExecutor)
    with WorkPool(2) as pool:
        thread = Thread(target=lambda: results.extend(pool.map(work, range(40))))
        thread.start()
        executor = _AdmissionExecutor.instances[0]
        assert executor.window_reached.wait(5)
        assert executor.submitted == 8
        assert executor.maximum == 8
        executor.allow_more.set()
        release.set()
        assert later_started.wait(5)
        thread.join(5)

    assert not thread.is_alive()
    assert results == list(range(40))
    assert executor.submitted == 40
    assert executor.maximum <= 4 * 2


def test_a_failing_document_raises_its_own_exception():
    """The pool never swallows a refusal — the parse's exception surfaces."""
    compiled = compile_text(GRAMMAR)
    pool = ParsePool(compiled.parse, cores=2)
    with pytest.raises(UnsupportedConstructError):
        pool.map(["(ok)", "nope"])
    pool.close()


def test_failure_reports_the_lowest_input_index_for_both_pool_facades():
    """A later fast failure cannot mask an earlier input's exception."""

    def work(item: int) -> int:
        if item == 0:
            sleep(0.05)
            raise ValueError("first input")
        raise KeyError("later input")

    with WorkPool(2) as pool:
        with pytest.raises(ValueError, match="first input"):
            pool.map(work, [0, 1])

    with ParsePool(work, cores=2) as pool:
        with pytest.raises(ValueError, match="first input"):
            pool.map([0, 1])


def test_explicit_cores_is_the_worker_count():
    """An explicit ask is a decision — used as given."""
    compiled = compile_text(GRAMMAR)
    assert ParsePool(compiled.parse, cores=3).workers == 3


def test_auto_sizing_follows_the_policy(monkeypatch: pytest.MonkeyPatch):
    """The pool's default is the policy's auto — one worker under the GIL."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: False)
    compiled = compile_text(GRAMMAR)
    assert ParsePool(compiled.parse).workers == 1
    assert ParsePool(compiled.parse, cores=1).workers == 1
