"""Tests for ``lexic.parsing.parallel.replicas`` — each worker's own tables.

A replica must be invisible: equal grammar, same classes, therefore equal
models. What it changes is which table objects a worker touches, which is
what stops concurrent parses contending on one set of refcount cache lines.

Ownership is the property these tests defend hardest. A replica belongs to one
THREAD: two threads that are alive at the same time must never be handed the
same one, however many pools, documents or first-touches are in flight.
"""

from __future__ import annotations

import threading

import pytest

from lexic.compile import compile_text
from lexic.ir import IrAst, IrNamedTuple
from lexic.parsing import parse_model
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.parallel import (
    Replica,
    document_view,
    replica_count,
    worker_parse,
    worker_replica,
)
from lexic.parsing.parallel import replicas as replica_module
from lexic.parsing.parallel.pool import WorkPool

TEXT = "- alpha\n- beta\n- gamma\n"


def _pair(name: str) -> Replica:
    """A grammar/binding pair no other test shares.

    Compilation is memoised per source, so a shared source would be a shared
    replica registry — and every count here would then depend on test order.
    """
    source = f'root ::= item+\nitem ::= "- " [a-z]+ "\\n"\n# {name}\n'
    compiled = compile_text(source)
    return compiled.codegen_grammar, compiled.product


def _in_thread(work) -> Replica:
    """Run ``work`` on a thread and join it, so its claim is a dead thread's."""
    got: list[Replica] = []
    thread = threading.Thread(target=lambda: got.append(work()))
    thread.start()
    thread.join()
    return got[0]


class _Recorder:
    """The real model product, recording what it was handed and returned."""

    def __init__(self) -> None:
        """Start with no calls recorded."""
        self.calls: list[tuple[IrAst, str, ModelExecutable, Resolver | None]] = []
        self.returned: list[IrNamedTuple] = []
        self.lock = threading.Lock()

    def __call__[M: IrNamedTuple](
        self,
        grammar: IrAst,
        text: str,
        binding: ModelExecutable[M],
        resolve: Resolver | None = None,
    ) -> M:
        """Parse as the product does, recording the request and the result."""
        model = parse_model(grammar, text, binding, resolve)
        with self.lock:
            self.calls.append((grammar, text, binding, resolve))
            self.returned.append(model)
        return model

    def views(self) -> set[int]:
        """The identities of the grammars this product was parsed against."""
        return {id(call[0]) for call in self.calls}


def test_a_replica_is_equal_but_distinct() -> None:
    """Equal by value (so models match), distinct by identity (so the
    engine's per-identity table memo gives it its own tables)."""
    grammar, binding = _pair("equal-but-distinct")
    replica_grammar, replica_binding = worker_replica(grammar, binding)

    assert replica_grammar == grammar
    assert replica_grammar is not grammar
    assert replica_binding is not binding


def test_replicas_build_the_same_models() -> None:
    """The whole point: replication changes timing, never values."""
    grammar, binding = _pair("same-models")
    original = parse_model(grammar, TEXT, binding)
    replica_grammar, replica_binding = worker_replica(grammar, binding)

    model = parse_model(replica_grammar, TEXT, replica_binding)

    assert model == original
    assert type(model) is type(original)
    assert model.to_text() == TEXT


def test_a_thread_keeps_the_replica_it_claimed() -> None:
    """Claimed once and kept — a discarded replica would pay its table
    compilation again on the next parse."""
    grammar, binding = _pair("kept")

    first = worker_replica(grammar, binding)
    second = worker_replica(grammar, binding)

    assert first is second
    assert replica_count(grammar, binding) == 1


def test_one_thread_claims_one_replica_per_pair() -> None:
    """Two artefacts on one thread are two claims, never one shared view."""
    grammar, binding = _pair("two-pairs-a")
    other_grammar, other_binding = _pair("two-pairs-b")

    mine = worker_replica(grammar, binding)
    theirs = worker_replica(other_grammar, other_binding)

    assert mine[0] is not theirs[0]
    assert replica_count(grammar, binding) == 1
    assert replica_count(other_grammar, other_binding) == 1


def _claim_together(grammar: IrAst, binding: ModelExecutable, count: int):
    """``count`` threads claiming at once, none exiting before all have."""
    started = threading.Barrier(count)
    finished = threading.Barrier(count)
    claimed: list[Replica] = []
    lock = threading.Lock()

    def claim() -> None:
        started.wait(timeout=30)
        replica = worker_replica(grammar, binding)
        with lock:
            claimed.append(replica)
        finished.wait(timeout=30)

    threads = [threading.Thread(target=claim) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return claimed


def test_concurrent_first_touches_allocate_exactly_one_replica_each() -> None:
    """Sixteen threads first-touching one pair mint sixteen replicas.

    Unsynchronised growth reads a stale population and mints against it: the
    same sixteen requests produced twenty-three to thirty-two replicas, so the
    count is the assertion and not just the distinctness.
    """
    grammar, binding = _pair("first-touch-race")

    claimed = _claim_together(grammar, binding, 16)

    assert len(claimed) == 16
    assert len({id(replica) for replica in claimed}) == 16
    assert len({id(replica[0]) for replica in claimed}) == 16
    assert len({id(replica[1]) for replica in claimed}) == 16
    assert replica_count(grammar, binding) == 16


def test_no_worker_is_handed_the_original_pair() -> None:
    """The submitting thread's own objects stay its own."""
    grammar, binding = _pair("original-pair")

    claimed = _claim_together(grammar, binding, 4)

    assert all(replica[0] is not grammar for replica in claimed)
    assert all(replica[1] is not binding for replica in claimed)


def _pool_views(
    pool: WorkPool, parse: _Recorder, arrived: threading.Barrier, ask: Replica
) -> None:
    """Run one worker_parse per pool worker, all four threads live at once."""
    grammar, binding = ask

    def work(index: int) -> IrNamedTuple:
        arrived.wait(timeout=30)
        return worker_parse(parse, grammar, f"- item{'ab'[index]}\n", binding, None)

    pool.map(work, list(range(pool.workers)))


def test_two_overlapping_pools_never_share_a_replica() -> None:
    """Pool-local worker numbers are not identities.

    Two live ``WorkPool(2)`` leases number their own threads 0 and 1, so any
    scheme indexing one shared list by that number hands both pools' slot 0 the
    same replica. Four live worker threads owe four distinct views.
    """
    grammar, binding = _pair("overlapping-pools")
    parse = _Recorder()
    arrived = threading.Barrier(4)

    with WorkPool(2) as one, WorkPool(2) as two:
        driver = threading.Thread(
            target=_pool_views, args=(one, parse, arrived, (grammar, binding))
        )
        driver.start()
        _pool_views(two, parse, arrived, (grammar, binding))
        driver.join(timeout=30)

    assert len(parse.calls) == 4
    assert len(parse.views()) == 4
    assert id(grammar) not in parse.views()
    assert replica_count(grammar, binding) == 4


def test_worker_parse_hands_the_product_this_threads_view() -> None:
    """Replica selection, forwarding and result identity, in one call."""
    grammar, binding = _pair("worker-parse-forwarding")
    parse = _Recorder()

    def resolve(first: ParseTree, _other: ParseTree) -> ParseTree:
        """The degenerate take-the-first resolver, here only to be forwarded."""
        return first

    returned = worker_parse(parse, grammar, "- one\n", binding, resolve)

    view_grammar, view_binding = worker_replica(grammar, binding)
    seen_grammar, seen_text, seen_binding, seen_resolve = parse.calls[0]
    assert len(parse.calls) == 1
    assert seen_grammar is view_grammar and seen_grammar is not grammar
    assert seen_binding is view_binding and seen_binding is not binding
    assert seen_text == "- one\n"
    assert seen_resolve is resolve
    assert returned is parse.returned[0]


def test_worker_parse_builds_the_model_the_sequential_parse_would() -> None:
    """The replica is invisible through the product the engine ships."""
    grammar, binding = _pair("worker-parse-model")

    model = worker_parse(parse_model, grammar, TEXT, binding, None)

    assert model == parse_model(grammar, TEXT, binding)
    assert model.to_text() == TEXT


def test_an_exited_workers_replica_is_dropped_rather_than_reissued() -> None:
    """A dead thread's claim is not inherited by the next worker.

    Its tables were allocated by that thread, so re-issuing them would hand a
    live worker the foreign objects the replica exists to avoid. The registry
    must not grow with every pool the process ever started either.
    """
    grammar, binding = _pair("exited-worker")

    first = _in_thread(lambda: worker_replica(grammar, binding))
    assert replica_count(grammar, binding) == 1

    second = _in_thread(lambda: worker_replica(grammar, binding))

    assert second[0] is not first[0]
    assert replica_count(grammar, binding) == 1


def test_a_live_workers_replica_survives_another_threads_claim() -> None:
    """Reclaiming reads liveness, not recency."""
    grammar, binding = _pair("live-worker")
    mine = worker_replica(grammar, binding)

    _in_thread(lambda: worker_replica(grammar, binding))

    assert worker_replica(grammar, binding) is mine
    assert replica_count(grammar, binding) == 2


def test_the_first_document_thread_keeps_the_original_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The submitting thread's own objects are the view it already has.

    Compiling a second product to hand the only thread in a single-threaded
    program a copy of what it already owns is pure cost.
    """
    monkeypatch.setattr(replica_module, "available_workers", lambda: 4)
    grammar, binding = _pair("document-thread")

    view = document_view(grammar, binding)

    assert view is binding
    assert document_view(grammar, binding) is view


def test_a_second_document_thread_gets_a_view_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two whole-document parses in flight contend exactly as chunk workers do."""
    monkeypatch.setattr(replica_module, "available_workers", lambda: 4)
    grammar, binding = _pair("second-document-thread")
    mine = document_view(grammar, binding)

    theirs = _in_thread(lambda: document_view(grammar, binding))

    assert mine is binding
    assert theirs is not binding
    assert replica_count(grammar, binding) == 2


def test_a_document_view_is_an_executable_and_a_worker_view_is_a_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The executable half is what privatises a parse; the grammar is shared.

    A product is memoised per ``(grammar, binding)`` identity and mints
    everything it holds, so a private binding IS a private set of tables. The
    split plan, the roles and every other analysis are memoised on the GRAMMAR,
    and a document thread keeps the artefact's — which is why its view is an
    executable and only a worker's carries a grammar of its own.
    """
    monkeypatch.setattr(replica_module, "available_workers", lambda: 4)
    grammar, binding = _pair("document-grammar-shared")
    document_view(grammar, binding)

    theirs = _in_thread(lambda: document_view(grammar, binding))
    worker = _in_thread(lambda: worker_replica(grammar, binding))

    assert theirs is not binding
    assert worker[0] is not grammar
    assert worker[1] is not binding


def test_a_worker_never_takes_the_original_even_when_it_is_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The document route's licence is not the worker route's.

    A chunk worker taking the original pair would parse against the objects the
    submitting thread allocated — and that thread is concurrently parsing the
    lead, the stand-in shell or the sequential fallback against them.
    """
    monkeypatch.setattr(replica_module, "available_workers", lambda: 4)
    grammar, binding = _pair("worker-never-original")

    view = worker_replica(grammar, binding)

    assert view[0] is not grammar
    assert view[1] is not binding
    assert document_view(grammar, binding) is view[1]


def test_a_document_thread_replicates_nothing_where_it_cannot_pay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequential callers and GIL builds get the original product back."""
    monkeypatch.setattr(replica_module, "available_workers", lambda: 1)
    grammar, binding = _pair("gil-build")

    view = document_view(grammar, binding)

    assert view is binding
    assert replica_count(grammar, binding) == 0
