"""A worker's replica is released when the worker actually exits.

`_reclaim` prunes only the pair being claimed against, so a pair no document
touches again keeps its dead claims for the life of the process. Measured
before this landed: one pass over a twelve-grammar roster left **189 of 203
claims held by threads that had already exited**, and eight further splits of
the first grammar did not move it.

The mechanism is a per-worker sentinel installed by the pool's initializer,
releasing the claims of the `Thread` it captured, finalized when that thread's
state is freed. `ThreadPoolExecutor` offers an initializer and no per-worker
exit callback, so object lifetime is the only signal available that fires for
every worker that ever claimed. Arming at CLAIM time rather than at worker
start is both cheaper and narrower: a worker that never claims holds nothing
to release, and a pool whose phases never touch the registry pays nothing.

What these cases defend is not that the release happens but that it happens to
the RIGHT claims: a running worker keeps its tables, the document thread keeps
its view, a live idle pool keeps its workers' replicas, and the deliberately
immediate failure path stays immediate.

Finalization is not synchronous with `shutdown()` returning, so every case
polls to a bounded deadline rather than asserting at once. The deadline is a
failure, not a pass.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from lexic.compile import compile_text
from lexic.parsing.parallel.pool import PoolLease, WorkPool, reset_pools
from lexic.parsing.parallel.replicas import (
    claim_census,
    retire_thread,
    worker_replica,
)
from tests.split_helpers import LEAD_RULE

DEADLINE = 5.0
"""Seconds a finalizer is given before the case fails."""


def claims() -> tuple[int, int]:
    """Live and dead claims across the whole registry, right now."""
    return claim_census()


def settled(want: int, which: int = 1) -> tuple[int, int]:
    """Poll until the chosen counter reaches ``want``, or the deadline fails."""
    end = time.monotonic() + DEADLINE
    counted = claims()
    while time.monotonic() < end and counted[which] != want:
        time.sleep(0.01)
        counted = claims()
    return counted


@pytest.fixture(name="artefact")
def _artefact():
    """A compiled pair and a document big enough to split, registry clean."""
    reset_pools()
    compiled = compile_text(LEAD_RULE, cache_key="replica-reclamation")
    text = ", ".join(f"key{'x' * (i % 7)}:{i}" for i in range(1500))
    yield compiled, text
    reset_pools()


# ── the release happens, and without a later parse ────────────────────────


def test_a_clean_close_leaves_no_dead_claim(artefact) -> None:
    """Workers that exited hold nothing, and no further parse is needed."""
    compiled, text = artefact
    compiled.parse(text, cores=8)
    reset_pools()
    live, dead = settled(0)
    assert dead == 0, f"{dead} claims outlived their threads"
    assert live >= 1, "the document thread's own claim must remain"


def test_a_pair_never_touched_again_is_still_cleaned(artefact) -> None:
    """The case `_reclaim` alone could not reach.

    A second pair is parsed and then abandoned. Nothing ever claims against it
    again, so the liveness sweep inside `_claim` never runs for it; only the
    workers' own exit signal can free it.
    """
    compiled, text = artefact
    other = compile_text(LEAD_RULE, cache_key="replica-reclamation-other")
    other.parse(text, cores=8)
    reset_pools()
    for _ in range(3):
        compiled.parse(text, cores=8)
        reset_pools()
    _live, dead = settled(0)
    assert dead == 0, f"the abandoned pair kept {dead} dead claims"


def test_every_worker_signals_even_when_the_work_did_not_visit_it() -> None:
    """A pool of sixteen given two items still frees all sixteen.

    A signal carried by the WORK would never fire for the fourteen workers it
    never reached, which is the argument for the initializer.
    """
    grammar = compile_text(LEAD_RULE, cache_key="replica-reclamation-wide")
    pair = (grammar.codegen_grammar, grammar.product)
    started: set[int] = set()
    lock = threading.Lock()

    def claim(_item: int) -> None:
        worker_replica(*pair)
        with lock:
            started.add(threading.get_ident())

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(claim, range(2)))
    assert len(started) < 16, "the fixture must leave workers unvisited"
    _live, dead = settled(0)
    assert dead == 0, f"{dead} claims left by workers that exited"


# ── the release does not take what is still in use ────────────────────────


def test_a_running_worker_keeps_its_replica(artefact) -> None:
    """A no-wait shutdown must not drop tables a worker is still parsing on."""
    compiled, _text = artefact
    pair = (compiled.codegen_grammar, compiled.product)
    entered = threading.Event()
    release = threading.Event()

    def hold(_item: int) -> int:
        worker_replica(*pair)
        entered.set()
        release.wait(DEADLINE)
        return 1

    before_live = claims()[0]
    pool = ThreadPoolExecutor(2)
    pool.submit(hold, 0)
    assert entered.wait(DEADLINE), "the worker never claimed"
    pool.shutdown(wait=False, cancel_futures=True)
    live_now = claims()[0]
    assert live_now > before_live, (
        "a live worker's claim was dropped during no-wait shutdown"
    )
    release.set()
    _live, dead = settled(0)
    assert dead == 0


def test_a_failed_pool_does_not_wait() -> None:
    """The deliberately immediate bug path stays immediate.

    Cleanup must not turn a failed pool's close into a wait: a sibling may be
    blocked on the very caller that is unwinding. The pool is failed the way a
    bug fails it — a non-`LexicError` out of the work — so this exercises the
    real state rather than one set by hand.
    """
    entered = threading.Event()
    release = threading.Event()

    def work(item: int) -> int:
        """Item 0 is the bug; item 1 is the sibling still running."""
        if item == 0:
            entered.wait(DEADLINE)
            raise ValueError("not a refusal — a bug")
        entered.set()
        release.wait(DEADLINE)
        return item

    pool = WorkPool(2)
    with pytest.raises(ValueError):
        pool.map(work, [0, 1])
    start = time.perf_counter()
    pool.close()
    elapsed = time.perf_counter() - start
    release.set()
    assert elapsed < 0.5, f"a failed pool's close took {elapsed * 1e3:.0f} ms"


def test_a_live_idle_pool_keeps_its_replicas(artefact) -> None:
    """A pool returned to the idle cache still owns its workers' tables."""
    compiled, text = artefact
    compiled.parse(text, cores=8)
    with PoolLease(8) as pool:
        assert pool.workers >= 2
        live, dead = claims()
    assert dead == 0
    assert live >= 1, "the idle pool's live workers must keep their claims"


def test_the_document_thread_keeps_its_view(artefact) -> None:
    """Nothing retires the submitting thread's own claim but its own exit."""
    compiled, text = artefact
    before = claims()[0]
    compiled.parse(text, cores=8)
    reset_pools()
    live, dead = settled(0)
    assert dead == 0
    assert live >= before, "the document thread's view was swept"
    assert compiled.parse(text, cores=1).to_text() == text


# ── the signal's own contract ─────────────────────────────────────────────


def test_retiring_a_thread_that_holds_nothing_is_harmless() -> None:
    """An exit signal from a worker that never claimed changes nothing."""
    before = claims()
    retire_thread(threading.Thread(target=lambda: None))
    assert claims() == before


def test_a_finalizer_cannot_identify_its_own_thread() -> None:
    """Why the `Thread` is captured at initializer time, proved not assumed.

    `threading.current_thread()` inside a finalizer running on a dying worker
    returns a dummy — so a signal that asked who it was at finalization would
    match no claim and retire nothing.
    """
    seen: list[bool] = []

    class Probe:
        """Compares the captured thread with what finalization can see."""

        def __init__(self, thread: threading.Thread) -> None:
            """Pin the thread this probe was made on."""
            self.thread = thread

        def __del__(self) -> None:
            """Record whether the dying thread can still name itself."""
            seen.append(threading.current_thread() is self.thread)

    local = threading.local()

    def arm() -> None:
        local.probe = Probe(threading.current_thread())

    with ThreadPoolExecutor(2, initializer=arm) as pool:
        list(pool.map(lambda _: None, range(4)))
    end = time.monotonic() + DEADLINE
    while time.monotonic() < end and not seen:
        time.sleep(0.01)
    assert seen, "no finalizer ran — the probe proved nothing"
    assert not any(seen), "a finalizer named its own thread; capture is moot"
