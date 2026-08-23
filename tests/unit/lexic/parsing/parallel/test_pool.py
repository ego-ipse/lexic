"""Tests for ``lexic.parsing.parallel.pool`` — the document pool.

The pool changes WHEN documents parse, never what a parse means: results
equal the sequential parses, in input order, and a failing document raises
its own exception.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack
from threading import Barrier, Event, Lock, Thread, active_count
from time import monotonic, sleep

import pytest

import lexic.parsing.parallel.pool as pool_module
from lexic.compile import compile_text, reset_cache_for_tests
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.parallel import ParsePool
from lexic.parsing.parallel import policy as policy_module
from lexic.parsing.parallel.pool import RETAINED, PoolLease, WorkPool
from tests.unit.lexic.parsing.parallel.test_orchestrate import LEAD_RULE
from tests.unit.lexic.parsing.parallel.test_orchestrate import _doc as _split_doc

GRAMMAR = 'root ::= "(" [a-z]+ ")"\n'


@pytest.fixture(autouse=True)
def _reset_pool_cache():
    """Empty the warm-pool cache before and after each test for isolation."""
    pool_module.reset_pools()
    yield
    pool_module.reset_pools()


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
        self.maximum = 0
        self.submitted = 0
        self.window_reached = Event()
        self.allow_more = Event()
        self._live: list[Future] = []
        self._lock = Lock()
        self.instances.append(self)

    def submit(self, work, *args, **kwargs):
        """Track a future before delegating to the real executor.

        The pending count is recomputed from the futures themselves rather
        than kept by a done-callback. A callback decrements whenever the
        future happens to finish, which is NOT ordered against ``map``
        popping that future and admitting its replacement — so the counter
        could read one above the real window for as long as a callback had
        not run yet, and the gate failed on an admission that never happened.
        Counting not-done futures AT SUBMIT TIME measures exactly what ``map``
        bounds, with no ordering assumption to lose.
        """
        with self._lock:
            self._live = [future for future in self._live if not future.done()]
            self.maximum = max(self.maximum, len(self._live) + 1)
            self.submitted += 1
            if self.submitted == 8:
                self.window_reached.set()
        if self.submitted == 8:
            assert self.allow_more.wait(5)
        future = self.executor.submit(work, *args, **kwargs)
        with self._lock:
            self._live.append(future)
        return future

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


def test_lease_reuses_the_same_pool_at_one_worker_count():
    """Two consecutive leases at the same width borrow one identical pool."""
    with PoolLease(3) as first:
        pass
    with PoolLease(3) as second:
        assert second is first
    with PoolLease(5) as third:
        assert third is not first


def test_lease_bounds_retained_pools_per_worker_count():
    """A third concurrently-released pool is closed, not kept idle.

    All three probe pools are exercised directly (never through another
    lease), so the count of survivors pins the retained-set size without
    reaching into the module's private cache.
    """
    with ExitStack() as stack:
        pools = [stack.enter_context(PoolLease(3)) for _ in range(3)]
        assert len({id(pool) for pool in pools}) == 3

    alive = 0
    closed = 0
    for pool in pools:
        try:
            pool.map(lambda item: item, [1])
            alive += 1
        except RuntimeError:
            closed += 1
    assert alive == RETAINED
    assert closed == 1


def test_lease_keeps_thread_count_stable_across_many_sequential_parses():
    """Sequential borrow/release never grows the retained thread count."""
    baseline = active_count()
    seen: set[int] = set()
    counts = []
    for _ in range(10):
        with PoolLease(3) as pool:
            seen.add(id(pool))
            pool.map(lambda item: item + 1, list(range(6)))
        counts.append(active_count())

    assert len(seen) == 1
    assert counts[-1] >= baseline
    assert len(set(counts[2:])) == 1


def test_lease_closes_the_pool_when_the_body_raises():
    """A phase that raises inside the lease closes that pool, not returns it."""
    borrowed: WorkPool | None = None
    with pytest.raises(ValueError, match="boom"):
        with PoolLease(2) as pool:
            borrowed = pool
            raise ValueError("boom")

    assert borrowed is not None
    with pytest.raises(RuntimeError, match="cannot schedule new futures"):
        borrowed.map(lambda item: item, [1])

    with PoolLease(2) as fresh:
        assert fresh is not borrowed
        assert fresh.map(lambda item: item * 2, [1, 2, 3]) == [2, 4, 6]


def test_lease_gives_concurrent_borrowers_distinct_pools():
    """Two threads borrowing the same width simultaneously never share one."""
    with PoolLease(2) as warm:
        pass
    barrier = Barrier(2)
    borrowed: list[WorkPool | None] = [None, None]
    results: list[list[int] | None] = [None, None]

    def borrow_and_work(index: int) -> None:
        with PoolLease(2) as pool:
            borrowed[index] = pool
            barrier.wait(5)
            results[index] = pool.map(lambda item: item * 2, [1, 2, 3])

    threads = [Thread(target=borrow_and_work, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert not any(thread.is_alive() for thread in threads)
    assert borrowed[0] is not None and borrowed[1] is not None
    assert borrowed[0] is not borrowed[1]
    assert warm in borrowed
    assert results == [[2, 4, 6], [2, 4, 6]]
    for pool in borrowed:
        assert pool is not None
        assert pool.map(lambda item: item, [7]) == [7]


def test_reset_pools_empties_the_idle_set_and_closes_its_pools():
    """``reset_pools`` clears every retained pool and shuts each one down."""
    with PoolLease(2) as pool:
        pool.map(lambda item: item, [1])
    with PoolLease(2) as same_pool:
        assert same_pool is pool

    pool_module.reset_pools()

    with pytest.raises(RuntimeError, match="cannot schedule new futures"):
        pool.map(lambda item: item, [1])
    with PoolLease(2) as fresh:
        assert fresh is not pool
        assert fresh.map(lambda item: item, [2]) == [2]


def test_reset_cache_for_tests_reaches_the_pool_seam():
    """The public compile-cache reset seam also empties the pool cache."""
    with PoolLease(2) as pool:
        pool.map(lambda item: item, [1])

    reset_cache_for_tests()

    with pytest.raises(RuntimeError, match="cannot schedule new futures"):
        pool.map(lambda item: item, [1])
    with PoolLease(2) as fresh:
        assert fresh is not pool


def test_reset_pools_returns_thread_count_to_baseline():
    """After a reset, worker threads wind down to the pre-lease count."""
    baseline = active_count()
    with PoolLease(3) as pool:
        pool.map(lambda item: item + 1, list(range(6)))

    pool_module.reset_pools()

    deadline = monotonic() + 2
    while active_count() > baseline and monotonic() < deadline:
        sleep(0.02)
    assert active_count() <= baseline


def test_split_parse_matches_sequential_across_many_warm_pool_reuses():
    """Warm-pool state never leaks between documents on the public seam."""
    compiled = compile_text(LEAD_RULE)
    texts = [_split_doc(400 + 25 * i) for i in range(12)]
    for text in texts:
        parallel = compiled.parse(text, cores=4)
        sequential = compiled.parse(text, cores=1)
        assert parallel == sequential
        assert parallel.to_text() == text
