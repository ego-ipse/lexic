"""A pool's replica claims are released when the pool dies, not at the next parse.

`_reclaim` used to run only inside `_claim`, so a dead pool's claims waited for
the next parse of that pair. Measured before this: after six splits at varied
worker counts, 82 of 85 claims sat on exited threads holding 377 memo entries,
and half a second later they still did.

Two paths reclaim, by different routes:

* a CLEAN close has already waited for its workers, so every one is gone and
  the crew's sweep finds them all;
* a FAILED close must not wait — that immediacy is the deadlock it exists to
  avoid — so each worker releases its own claims as it dies, and whichever
  exits last sweeps the residue.

What must survive both: the document thread's own view, and a live idle pool's
replicas. The rules the prototype named are the tests here.
"""

from __future__ import annotations

import threading
import time

import pytest

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.caches import cached_entries, reset_caches
from lexic.parsing.parallel import replicas as registry
from lexic.parsing.parallel.pool import PoolLease, WorkPool, reset_pools
from lexic.parsing.parallel.replicas import replica_count
from lexic.parsing.products import parse_model

GRAMMAR = 'root ::= line+\nline ::= [a-z0-9 ]+ nl\nnl ::= "\\n"\n'
"""A flat, cheap grammar — the reclamation is about pools, not about parsing."""

SETTLE = 5.0
"""Seconds to allow a worker to actually die. Polled, never joined."""


def pair():
    """A fresh artefact and its binding, cache-isolated from other tests."""
    compiled = compile_text(GRAMMAR, cache_key=f"reclaim-{time.monotonic_ns()}")
    return compiled.codegen_grammar, compiled.product


def claims_of(grammar, binding) -> int:
    """How many claims the registry holds for this pair."""
    return replica_count(grammar, binding)


def settle_until(predicate, seconds: float = SETTLE) -> bool:
    """Poll ``predicate`` rather than joining — joining is what must not happen."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def claim_on_workers(pool: WorkPool, grammar, binding, count: int) -> None:
    """Make every worker of ``pool`` claim a replica for the pair.

    The barrier is what forces ``count`` DISTINCT workers to hold a claim at
    once: without it one worker can run every task and the pool never spawns a
    second.
    """
    arrived = threading.Barrier(count, timeout=SETTLE)

    def work(_n: int) -> int:
        registry.worker_replica(grammar, binding)
        arrived.wait()
        return 0

    pool.map(work, list(range(count)))


def fail_the_pool(pool: WorkPool) -> None:
    """Retire ``pool`` the way a bug does, through its own map.

    A bug — not a `LexicError`, which is a verdict about an input — is what
    marks a pool failed, cancels its queued work and takes the no-wait close.
    Driving it through `map` rather than setting the flag keeps the test on
    the path production takes.
    """

    def boom(_n: int) -> int:
        raise ZeroDivisionError("a bug, not a verdict")

    with pytest.raises(ZeroDivisionError):
        pool.map(boom, [0])


def parse_on_workers(pool: WorkPool, grammar, binding, count: int) -> None:
    """Make every worker PARSE through its own replica.

    Claiming alone mints a binding copy and little else; the tables a replica
    exists to privatise are built by the first parse through it, and those are
    the memo entries a release has to take.
    """
    arrived = threading.Barrier(count, timeout=SETTLE)

    def work(n: int) -> int:
        registry.worker_parse(parse_model, grammar, f"worker {n} line\n", binding, None)
        arrived.wait()
        return 0

    pool.map(work, list(range(count)))


# ── path (a): a clean close awaits and prunes ─────────────────────────────


def test_a_clean_close_releases_its_workers_claims() -> None:
    """No later parse: the pool waited, so its claims go with it."""
    reset_pools()
    grammar, binding = pair()
    pool = WorkPool(2)
    claim_on_workers(pool, grammar, binding, 2)
    assert claims_of(grammar, binding) == 2, "the workers must have claimed"

    pool.close()
    assert claims_of(grammar, binding) == 0, (
        "a clean close has already waited, so nothing should be left to find"
    )


def test_reset_pools_releases_the_idle_pools_claims() -> None:
    """`reset_pools` closes cleanly, so it takes path (a)."""
    reset_pools()
    grammar, binding = pair()
    with PoolLease(2) as pool:
        claim_on_workers(pool, grammar, binding, 2)
    assert claims_of(grammar, binding) == 2, "an idle pool's workers are still live"

    reset_pools()
    assert claims_of(grammar, binding) == 0


def test_a_live_idle_pools_replicas_are_preserved() -> None:
    """A returned pool is warm, not dead — its workers still own their views."""
    reset_pools()
    grammar, binding = pair()
    with PoolLease(2) as pool:
        claim_on_workers(pool, grammar, binding, 2)

    assert claims_of(grammar, binding) == 2
    assert settle_until(lambda: claims_of(grammar, binding) == 2, seconds=0.5), (
        "an idle pool's claims must not drain while it waits to be reused"
    )
    reset_pools()


# ── path (b): a failed pool keeps its immediacy ───────────────────────────


def hold_workers(pool: WorkPool, grammar, binding, count: int):
    """Occupy ``count`` workers until the returned event is set.

    Through the pool's own ``map``, on a background thread, so the work is
    genuinely in flight when the pool is closed — which is the state both
    tests below are about, and the one a drained ``map`` cannot produce.
    """
    holding = threading.Event()
    release_them = threading.Event()

    def slow(_n: int) -> int:
        registry.worker_replica(grammar, binding)
        holding.set()
        release_them.wait(timeout=SETTLE)
        return 0

    runner = threading.Thread(
        target=lambda: pool.map(slow, list(range(count))), daemon=True
    )
    runner.start()
    assert holding.wait(timeout=SETTLE), "the workers never took the work"
    return release_them, runner


def test_a_failed_close_does_not_wait() -> None:
    """The deliberately immediate bug path stays immediate."""
    reset_pools()
    grammar, binding = pair()
    pool = WorkPool(4)  # three held, one spare for the bug
    release_them, runner = hold_workers(pool, grammar, binding, 3)
    fail_the_pool(pool)

    started = time.perf_counter()
    pool.close()
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0, f"a failed close waited {elapsed:.2f}s for its workers"

    release_them.set()
    runner.join(timeout=SETTLE)


def test_a_failed_pools_claims_are_released_without_another_parse() -> None:
    """Each worker releases its own as it dies; no parse of the pair follows."""
    reset_pools()
    grammar, binding = pair()
    pool = WorkPool(2)
    claim_on_workers(pool, grammar, binding, 2)
    assert claims_of(grammar, binding) == 2

    fail_the_pool(pool)
    pool.close()
    assert settle_until(lambda: claims_of(grammar, binding) == 0), (
        "the workers' own exits must release their claims"
    )


def test_a_failed_close_releases_nothing_while_workers_run() -> None:
    """Tables in use are not dropped by a shutdown that did not wait."""
    reset_pools()
    grammar, binding = pair()
    pool = WorkPool(3)  # two held, one spare for the bug
    release_them, runner = hold_workers(pool, grammar, binding, 2)
    fail_the_pool(pool)
    pool.close()

    assert claims_of(grammar, binding) > 0, (
        "a claim was dropped while its worker was still parsing against it"
    )
    release_them.set()
    runner.join(timeout=SETTLE)
    assert settle_until(lambda: claims_of(grammar, binding) == 0)


# ── what must survive ─────────────────────────────────────────────────────


def test_the_document_threads_own_view_is_never_swept() -> None:
    """The submitting thread carries no crew, so no pool's sweep can see it."""
    reset_pools()
    grammar, binding = pair()
    mine = registry.worker_replica(grammar, binding)  # this thread, no crew
    before = claims_of(grammar, binding)

    pool = WorkPool(2)
    claim_on_workers(pool, grammar, binding, 2)
    pool.close()

    assert claims_of(grammar, binding) == before, (
        "the live document thread's claim was swept with the pool's"
    )
    assert registry.worker_replica(grammar, binding) is mine, (
        "and it still resolves to the same view"
    )


def test_a_live_pairs_memo_entries_survive_a_workers_release() -> None:
    """`caches.release` drops what the worker minted, not what the pair owns.

    The question the prototype could not answer, because it modelled the
    registry and not the memos: releasing a dead worker's identities must not
    take entries the artefact itself still owns — the pair is alive and about
    to be parsed again.
    """
    reset_caches()
    reset_pools()
    grammar, binding = pair()
    parse_model(grammar, "alpha\n", binding)  # the pair's own entries exist
    owned = cached_entries()
    assert owned > 0, "the pair must have memo entries for this to mean anything"

    pool = WorkPool(2)
    parse_on_workers(pool, grammar, binding, 2)
    minted = cached_entries()
    assert minted > owned, "the workers must have minted entries of their own"

    pool.close()
    after = cached_entries()
    assert after < minted, f"the workers' entries were not released: {minted} → {after}"
    assert after >= owned, (
        f"the release took the live pair's own entries: {owned} → {after}"
    )
    assert parse_model(grammar, "beta\n", binding) is not None, (
        "and the pair still parses without recompiling into an error"
    )


def test_a_split_still_parses_after_its_pool_is_reclaimed() -> None:
    """End to end: reclamation changes no answer."""
    reset_pools()
    compiled = compile_text(GRAMMAR, cache_key="reclaim-end-to-end")
    text = "".join(f"line {n} of text\n" for n in range(4000))
    first = compiled.parse(text, cores=4)
    reset_pools()
    second = compiled.parse(text, cores=4)
    assert first == second
    assert second.to_text() == text


def test_the_registry_does_not_accumulate_across_pools() -> None:
    """The leak this exists to close, stated as a bound."""
    reset_pools()
    grammar, binding = pair()
    for _round in range(6):
        pool = WorkPool(2)
        claim_on_workers(pool, grammar, binding, 2)
        pool.close()
    assert claims_of(grammar, binding) == 0, "a dead thread's claim outlived its pool"


@pytest.mark.parametrize("failed", [False, True])
def test_a_pool_that_ran_fewer_tasks_than_workers_still_closes(failed: bool) -> None:
    """An executor spawns lazily, so the count must be of STARTED workers.

    A pool sized for eight running two tasks starts two threads. Anything
    counting down from the requested width never reaches zero, and the claims
    would never be swept.
    """
    reset_pools()
    grammar, binding = pair()
    pool = WorkPool(8)
    claim_on_workers(pool, grammar, binding, 2)
    assert claims_of(grammar, binding) == 2

    if failed:
        fail_the_pool(pool)
    pool.close()
    assert settle_until(lambda: claims_of(grammar, binding) == 0), (
        f"a pool sized 8 that started 2 workers never closed (failed={failed})"
    )


def test_a_refused_split_reclaims_its_workers_and_keeps_the_driver() -> None:
    """A refusal retires the pool; the thread that asked is still parsing.

    The refusal is a verdict, not a bug, so the lease closes the pool cleanly
    and its workers' claims go — but the DOCUMENT thread made a claim too, for
    the sequential fallback, and it is alive and carries no crew. One claim
    must remain, and it must be the caller's own.
    """
    reset_pools()
    compiled = compile_text(GRAMMAR, cache_key="reclaim-refused")
    grammar, binding = compiled.codegen_grammar, compiled.product
    with pytest.raises(LexicError):
        compiled.parse("no trailing newline and a ; that cannot parse", cores=4)

    assert settle_until(lambda: claims_of(grammar, binding) <= 1), (
        "a worker's claim outlived the refused split"
    )
    mine = registry.worker_replica(grammar, binding)
    assert claims_of(grammar, binding) == 1, (
        "the driver's own claim was swept, or a worker's survived"
    )
    assert registry.worker_replica(grammar, binding) is mine
