"""Forking a process that holds live pool threads.

A forked child inherits every lock in whatever state its owning thread left
it, and only the forking thread exists on the other side — so a lock held by a
worker thread at the moment of the fork is held forever in the child. That is
not hypothetical: a split parse retains warm pools, and a helper that forks
after one has run is exactly the shape that deadlocked.

**What is assertable, and what is not.** Asserting "the child deadlocks
without the reset" would be asserting a bug, and it is not stable across
platforms — a pin that fails the day CPython improves points the wrong way.
What IS deterministic is the hazard's precondition and the fix's effect, so
those are what this pins.

One trap is recorded here as an assertion rather than a comment, because it
silently makes fork tests vacuous: **a non-empty ``_IDLE`` does not mean a
split engaged.** ``split_model`` takes its lease before deciding, so a
declining grammar leaves a retained pool whose executor owns zero threads. An
engaging parse leaves at least one thread in a retained executor. The tests
inspect those owned executor thread sets directly; the process-global thread
count includes unrelated runtime threads and is not evidence about this pool.
"""

from __future__ import annotations

import multiprocessing
import multiprocessing.queues
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import cast

from lexic.compile import CompiledGrammar, compile_text
from lexic.parsing.parallel import reset_pools
from lexic.parsing.parallel.pool import _IDLE
from tests.integration.lexic.concurrency.fixtures import (
    FLAT,
    SPLITTING,
    flat_doc,
    split_doc,
)

WORKERS = 8
CHILD_TIMEOUT = 60.0


def _retained_executor_threads() -> set[threading.Thread]:
    """Return the threads owned by every executor retained in ``_IDLE``."""
    return {
        thread
        for waiting in _IDLE.values()
        for work_pool in waiting
        for thread in cast(
            set[threading.Thread],
            vars(cast(ThreadPoolExecutor, vars(work_pool)["_pool"]))["_threads"],
        )
    }


def _split_parse() -> CompiledGrammar:
    """Run one engaging split parse and hand back the artefact it used."""
    compiled = compile_text(SPLITTING, cache_key="concurrency-fork")
    text = split_doc()
    assert compiled.parse(text, cores=WORKERS).to_text() == text
    return compiled


def _child_parses(queue: multiprocessing.queues.Queue[str]) -> None:
    """Child-process body: parse in the fork and report the round-trip."""
    compiled = compile_text(SPLITTING, cache_key="concurrency-fork")
    text = split_doc(0, 40)
    queue.put(compiled.parse(text, cores=1).to_text())


def test_a_retained_pool_does_not_prove_a_split_engaged() -> None:
    """The vacuity trap, pinned: ``_IDLE`` fills even when nothing split.

    The lease is taken before the plan is consulted, so a declining grammar
    leaves a retained pool that owns no threads at all. Anything using
    ``_IDLE`` as an engagement witness is measuring the wrong thing.
    """
    reset_pools()
    compiled = compile_text(FLAT, cache_key="concurrency-declines")
    text = flat_doc(0, 3000)
    assert compiled.parse(text, cores=WORKERS).to_text() == text
    assert _IDLE, "expected the declining parse to retain a pool anyway"
    assert not _retained_executor_threads(), "the declining parse submitted work"


def test_an_engaging_split_parse_leaves_live_pool_threads() -> None:
    """The precondition that makes forking dangerous.

    A floor rather than an exact count: ``ThreadPoolExecutor`` spawns lazily,
    so how many of the eight workers exist depends on how much of the split
    ran concurrently. What must hold is that the retained executor owns a live
    worker, which is exactly the state a later fork must not inherit.
    """
    reset_pools()
    assert not _retained_executor_threads(), "reset left executor threads behind"
    _split_parse()
    assert _IDLE, "no pool was retained"
    assert any(thread.is_alive() for thread in _retained_executor_threads()), (
        "the engaging parse retained no live worker"
    )


def test_reset_pools_closes_all_retained_executor_threads() -> None:
    """The fix leaves no retained executor worker thread to inherit."""
    _split_parse()
    retained = _retained_executor_threads()
    assert any(thread.is_alive() for thread in retained)
    reset_pools()
    assert not _IDLE
    assert not any(thread.is_alive() for thread in retained)


def test_a_forked_child_parses_after_the_pools_are_reset() -> None:
    """Reset, fork, and the child completes real work inside the deadline.

    The child's work is a PARSE, not arithmetic. That matters: arithmetic
    never needs the locks the inherited worker threads hold, so it completes
    happily beside a state that would deadlock work of a different shape, and
    a test built on it cannot fail. A child that inherited a held lock does
    not fail either — it waits — so the real answer arriving inside the
    deadline IS the evidence.
    """
    _split_parse()
    reset_pools()
    context = multiprocessing.get_context("fork")
    queue: multiprocessing.queues.Queue[str] = context.Queue()
    child = context.Process(target=_child_parses, args=(queue,))
    child.start()
    try:
        child.join(CHILD_TIMEOUT)
        assert not child.is_alive(), (
            f"the forked child was still running after {CHILD_TIMEOUT}s — "
            "this is the fork-with-live-threads deadlock"
        )
        assert queue.get(timeout=10.0) == split_doc(0, 40)
    finally:
        if child.is_alive():
            child.kill()
        child.join()
