"""Tests for ``lexic.parsing.parallel.replicas`` — each worker's own tables.

A replica must be invisible: equal grammar, same classes, therefore equal
models. What it changes is which table objects a worker touches, which is
what stops concurrent parses contending on one set of refcount cache lines.

Ownership is the property these tests defend hardest. A replica belongs to one
THREAD: two threads that are alive at the same time must never be handed the
same one, however many pools, documents or first-touches are in flight.
"""

from __future__ import annotations

import gc
import sys
import threading
from collections.abc import Callable
from re import Pattern
from types import CodeType, ModuleType

import pytest

from lexic.compile import compile_text
from lexic.ir import IrAst, IrNamedTuple, IrSelf
from lexic.parsing import DEFAULT_CONFIG, ParseConfig, parse_model
from lexic.parsing import products as products_module
from lexic.parsing.caches import release
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.executable import ModelExecutable, process_constants
from lexic.parsing.parallel import (
    Replica,
    document_view,
    replica_count,
)
from lexic.parsing.parallel import replicas as replica_module
from lexic.parsing.parallel import (
    worker_parse,
    worker_replica,
)
from lexic.parsing.parallel.pool import WorkPool
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler import delegate_compile as delegate_module
from lexic.parsing.pda.compiler import tables as pda_tables_module
from lexic.parsing.products import model_product
from tests.split_helpers import hold_workers, settled_replica_count

TEXT = "- alpha\n- beta\n- gamma\n"


def _pair(name: str) -> Replica:
    """A grammar/binding pair no other test shares.

    Compilation is memoised per source, so a shared source would be a shared
    replica registry — and every count here would then depend on test order.
    """
    source = f'root ::= item+\nitem ::= "- " [a-z]+ "\\n"\n# {name}\n'
    compiled = compile_text(source)
    return compiled.codegen_grammar, compiled.product


def _in_thread[T](work: Callable[[], T]) -> T:
    """Run ``work`` on a thread and join it, so its claim is a dead thread's."""
    got: list[T] = []
    thread = threading.Thread(target=lambda: got.append(work()))
    thread.start()
    thread.join()
    return got[0]


class _Recorder:
    """The real model product, recording what it was handed and returned."""

    def __init__(self) -> None:
        """Start with no calls recorded."""
        self.calls: list[tuple[IrAst, str, ModelExecutable, ParseConfig]] = []
        self.returned: list[IrNamedTuple] = []
        self.lock = threading.Lock()

    def __call__[M: IrNamedTuple](
        self,
        grammar: IrAst,
        text: str,
        binding: ModelExecutable[M],
        config: ParseConfig = DEFAULT_CONFIG,
    ) -> M:
        """Parse as the product does, recording the request and the result."""
        model = parse_model(grammar, text, binding, config)
        with self.lock:
            self.calls.append((grammar, text, binding, config))
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
    """``count`` threads claiming at once, none exiting before all have.

    The registry is read AT the finish barrier, while every claimant is still
    alive. A worker releases its claim when it exits, so a count taken after
    the join would measure reclamation instead of allocation.
    """
    started = threading.Barrier(count)
    claimed: list[Replica] = []
    live: list[int] = []
    lock = threading.Lock()

    # Read in the barrier's ACTION, which runs once when the barrier trips and
    # BEFORE any waiter is released. Reading after release is a race: the
    # barrier frees all sixteen at once and the first to look has already lost
    # some of the others to their own exit signals.
    finished = threading.Barrier(
        count, action=lambda: live.append(replica_count(grammar, binding))
    )

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
    return claimed, live[0]


def test_concurrent_first_touches_allocate_exactly_one_replica_each() -> None:
    """Sixteen threads first-touching one pair mint sixteen replicas.

    Unsynchronised growth reads a stale population and mints against it: the
    same sixteen requests produced twenty-three to thirty-two replicas, so the
    count is the assertion and not just the distinctness.
    """
    grammar, binding = _pair("first-touch-race")

    claimed, live = _claim_together(grammar, binding, 16)

    assert len(claimed) == 16
    assert len({id(replica) for replica in claimed}) == 16
    assert len({id(replica[0]) for replica in claimed}) == 16
    assert len({id(replica[1]) for replica in claimed}) == 16
    assert live == 16, f"the registry held {live} while all sixteen were alive"


def test_no_worker_is_handed_the_original_pair() -> None:
    """The submitting thread's own objects stay its own."""
    grammar, binding = _pair("original-pair")

    claimed, _live = _claim_together(grammar, binding, 4)

    assert all(replica[0] is not grammar for replica in claimed)
    assert all(replica[1] is not binding for replica in claimed)


def _pool_views(
    pool: WorkPool, parse: _Recorder, arrived: threading.Barrier, ask: Replica
) -> None:
    """Run one worker_parse per pool worker, all four threads live at once."""
    grammar, binding = ask

    def work(index: int) -> IrNamedTuple:
        arrived.wait(timeout=30)
        return worker_parse(
            parse, grammar, f"- item{'ab'[index]}\n", binding, DEFAULT_CONFIG
        )

    pool.map(work, list(range(pool.workers)))


def _both_pools(one: WorkPool, two: WorkPool, parse: _Recorder, ask: Replica) -> None:
    """One split in each pool at once — four worker threads live together."""
    arrived = threading.Barrier(4)
    driver = threading.Thread(target=_pool_views, args=(one, parse, arrived, ask))
    driver.start()
    _pool_views(two, parse, arrived, ask)
    driver.join(timeout=30)


def test_two_overlapping_pools_never_share_a_replica() -> None:
    """Pool-local worker numbers are not identities.

    Two live ``WorkPool(2)`` leases number their own threads 0 and 1, so any
    scheme indexing one shared list by that number hands both pools' slot 0 the
    same replica. Four live worker threads owe four distinct views.
    """
    grammar, binding = _pair("overlapping-pools")
    first, parse = _Recorder(), _Recorder()

    with WorkPool(2) as one, WorkPool(2) as two:
        # A first split runs on the original; the copies are earned in the next.
        _both_pools(one, two, first, (grammar, binding))
        _both_pools(one.lend(), two.lend(), parse, (grammar, binding))
        live_count = replica_count(grammar, binding)

    assert first.views() == {id(grammar)}

    assert len(parse.calls) == 4
    assert len(parse.views()) == 4
    assert id(grammar) not in parse.views()
    # Counted while the four workers were alive. The count AFTER their pools
    # close is not this test's subject and is no longer four: a worker releases
    # its claim when it exits, so a post-hoc count measures reclamation rather
    # than whether two live pools ever shared a view.
    assert live_count == 4
    assert replica_count(grammar, binding) <= 1


def test_worker_parse_hands_the_product_this_threads_view() -> None:
    """Replica selection, forwarding and result identity, in one call."""
    grammar, binding = _pair("worker-parse-forwarding")
    parse = _Recorder()

    def resolve(first: ParseTree, _other: ParseTree) -> ParseTree:
        """The degenerate take-the-first resolver, here only to be forwarded."""
        return first

    config = ParseConfig(resolve=resolve)
    returned = worker_parse(parse, grammar, "- one\n", binding, config)

    view_grammar, view_binding = worker_replica(grammar, binding)
    seen_grammar, seen_text, seen_binding, seen_config = parse.calls[0]
    assert len(parse.calls) == 1
    assert seen_grammar is view_grammar and seen_grammar is not grammar
    assert seen_binding is view_binding and seen_binding is not binding
    assert seen_text == "- one\n"
    assert seen_config is config
    assert returned is parse.returned[0]


def test_worker_parse_builds_the_model_the_sequential_parse_would() -> None:
    """The replica is invisible through the product the engine ships."""
    grammar, binding = _pair("worker-parse-model")

    model = worker_parse(parse_model, grammar, TEXT, binding, DEFAULT_CONFIG)

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
    # The thread has already exited, so its own exit signal has released the
    # claim: the registry does not grow with every pool the process started.
    assert settled_replica_count(grammar, binding, 0) == 0

    second = _in_thread(lambda: worker_replica(grammar, binding))

    assert second[0] is not first[0], "a dead thread's tables were re-issued"
    assert settled_replica_count(grammar, binding, 0) == 0


def test_a_live_workers_replica_survives_another_threads_claim() -> None:
    """Reclaiming reads liveness, not recency."""
    grammar, binding = _pair("live-worker")
    mine = worker_replica(grammar, binding)

    _in_thread(lambda: worker_replica(grammar, binding))

    assert worker_replica(grammar, binding) is mine
    # One live claim — this thread's. The other thread has exited and released
    # its own, which is liveness deciding the answer rather than recency.
    assert settled_replica_count(grammar, binding, 1) == 1


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
    assert settled_replica_count(grammar, binding, 1) == 1, (
        "the exited second document thread must have released its own view"
    )


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


# ── a replica's products are private copies of the original's ─────────────

ISLANDED = (
    'root ::= "<" run ">"\nrun ::= item item+\nitem ::= "[" w "]"\n'
    'w ::= v "x" | v "y"\nv ::= [a]*\n'
)
"""``run`` is an island whose interior delegates ``w``'s arms to clones: the
product, an island's tables and its delegates are all compiled artefacts."""

ISLANDED_TEXT = "<[aax][ay]>"


def _islanded(name: str) -> Replica:
    """An :data:`ISLANDED` pair no other test shares."""
    compiled = compile_text(f"{ISLANDED}# {name}\n")
    return compiled.codegen_grammar, compiled.product


def _parsed_view(grammar: IrAst, binding: ModelExecutable) -> Replica:
    """The calling thread's view, after parsing :data:`ISLANDED_TEXT` on it."""
    view = worker_replica(grammar, binding)
    parse_model(view[0], ISLANDED_TEXT, view[1])
    return view


def _worker_parse(grammar: IrAst, binding: ModelExecutable) -> Replica:
    """Parse :data:`ISLANDED_TEXT` on a worker's own view, on a thread."""
    return _in_thread(lambda: _parsed_view(grammar, binding))


_KEPT_TYPES = (str, int, float, bool, type(None), Pattern, type, ModuleType, CodeType)


def _ir_leaf(node: IrSelf) -> bool:
    """An IR value the copy keeps: one that rebuilds as itself."""
    if not isinstance(node, (tuple, str, int)):
        return False
    return node.rebuild(list(node.children())) is node


def _reach(roots: tuple[object, ...], kept: set[int]) -> dict[int, object]:
    """Every object reachable from ``roots`` that a copy would make anew.

    Atoms, classes, IR leaves that rebuild as themselves, module namespaces
    and the objects in ``kept`` end the walk; so does a lazy cache's ``origin``, the edge a copy
    asks its original through on a miss and never on a hit.
    """
    seen: dict[int, object] = {}
    stack = list(roots)
    while stack:
        part = stack.pop()
        if id(part) in seen or id(part) in kept or isinstance(part, _KEPT_TYPES):
            continue
        if isinstance(part, IrSelf) and _ir_leaf(part):
            continue
        seen[id(part)] = part
        origin = (
            getattr(part, "origin", None) if hasattr(type(part), "__slots__") else None
        )
        stack.extend(one for one in gc.get_referents(part) if one is not origin)
    return seen


def test_a_replicas_product_shares_no_engine_object_with_the_original() -> None:
    """The copy is private all the way down: past the atoms, the immutable IR
    values and the binding's read-only projections, nothing the replica's
    parse reads is an object the original's parse reads too."""
    grammar, binding = _islanded("census")
    parse_model(grammar, ISLANDED_TEXT, binding)
    original = model_product(grammar, binding)
    replica = _in_thread(lambda: model_product(*_parsed_view(grammar, binding)))
    kept = {id(value) for value in process_constants().values()}
    kept |= {id(binding.program), id(binding.codes), id(binding.routines)}
    kept |= {id(routine) for routine in binding.routines.values()}
    kept |= {id(vars(module)) for module in list(sys.modules.values()) if module}

    ours = _reach((original.pda, original.tables), kept)
    theirs = _reach((replica.pda, replica.tables), kept)

    assert replica.pda.origin is original.pda
    assert replica.pda.island_tables("run") is not original.pda.island_tables("run")
    assert len(theirs) > 100, "the census walked nothing"
    shared = [type(ours[at]).__qualname__ for at in set(ours) & set(theirs)]
    assert not shared, shared


def _counted(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count every grammar analysis the test triggers — each program compile,
    a delegate's included, starts with one."""
    counts = {"analysis": 0}
    analyse = GrammarAnalysis.__init__

    def analysis(self, *args, **kwargs):
        counts["analysis"] += 1
        analyse(self, *args, **kwargs)

    monkeypatch.setattr(GrammarAnalysis, "__init__", analysis)
    return counts


def test_a_replica_compiles_nothing_however_many_workers_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two workers meeting an uncompiled pair compile it once, on the original,
    and copy it: the count is what one sequential parse compiles, whichever
    thread got there first."""
    counts = _counted(monkeypatch)
    alone, alone_binding = _islanded("compiled-once-sequential")
    parse_model(alone, ISLANDED_TEXT, alone_binding)
    sequential = dict(counts)
    counts.update(analysis=0)
    grammar, binding = _islanded("compiled-once-workers")

    threads = [
        threading.Thread(target=_worker_parse, args=(grammar, binding))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sequential["analysis"] > 1
    assert counts == sequential


def _refused(_key: tuple[object, ...]):
    """A compile-once lock no hit may ask for."""
    raise AssertionError("a held artefact asked for its compile lock")


def test_a_held_artefact_is_read_without_a_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The miss lock is the miss path's: once the original and a replica hold
    their product, island tables and delegates, parsing takes no lock."""
    grammar, binding = _islanded("hit-without-lock")
    parse_model(grammar, ISLANDED_TEXT, binding)
    view = worker_replica(grammar, binding)
    parse_model(view[0], ISLANDED_TEXT, view[1])
    monkeypatch.setattr(pda_tables_module, "once", _refused)
    monkeypatch.setattr(delegate_module, "once", _refused)
    monkeypatch.setattr(products_module, "once", _refused)

    assert parse_model(grammar, ISLANDED_TEXT, binding).to_text() == ISLANDED_TEXT
    assert parse_model(view[0], ISLANDED_TEXT, view[1]).to_text() == ISLANDED_TEXT


# ── a replica is earned by reuse ─────────────────────────────────────────


def _split(pool: WorkPool, parse: _Recorder, ask: Replica) -> None:
    """One split over both of a two-worker pool's threads."""
    pool.lend()
    _pool_views(pool, parse, threading.Barrier(pool.workers), ask)


def test_a_one_shot_split_mints_nothing() -> None:
    """Every worker of a pair's first split parses against the original: a copy
    would cost more than the contention it saves, and outlive the split."""
    grammar, binding = _pair("one-shot")
    parse = _Recorder()

    with WorkPool(2) as pool:
        _split(pool, parse, (grammar, binding))
        assert replica_count(grammar, binding) == 0

    assert parse.views() == {id(grammar)}


def test_a_pair_met_again_mints_once_per_thread() -> None:
    """A thread that meets the pair in a later split copies it then, and keeps
    that copy for every split after."""
    grammar, binding = _pair("met-again")
    second, third = _Recorder(), _Recorder()

    with WorkPool(2) as pool:
        _split(pool, _Recorder(), (grammar, binding))
        _split(pool, second, (grammar, binding))
        minted = replica_count(grammar, binding)
        _split(pool, third, (grammar, binding))
        assert replica_count(grammar, binding) == minted == 2

    assert id(grammar) not in second.views()
    assert len(second.views()) == 2
    assert third.views() == second.views()


def test_a_splits_first_meetings_are_copied_before_the_pools_next_split() -> None:
    """Workers that met a pair on its original in one split each hold their own
    copy before the pool's next split dispatches a piece, so that split's pieces
    read copies and make none."""
    grammar, binding = _pair("warm-before-next-split")
    first, then = _Recorder(), _Recorder()

    with WorkPool(2) as pool:
        _pool_views(pool, first, threading.Barrier(2), (grammar, binding))
        replica_module.settle_first_meetings(pool, binding)
        before = replica_count(grammar, binding)
        replica_module.warm_due(pool.lend(), binding)
        warmed = replica_count(grammar, binding)
        _pool_views(pool, then, threading.Barrier(2), (grammar, binding))
        after = replica_count(grammar, binding)

    assert first.views() == {id(grammar)}, "a first meeting reads the original"
    assert before == 0, "nothing is copied until the warm"
    assert warmed == 2, "the warm gives every worker its own copy"
    assert len(then.views()) == 2 and id(grammar) not in then.views()
    assert after == warmed, "the next split's pieces made no copy"


def test_a_pool_owing_nothing_warms_nothing() -> None:
    """With no first meeting settled on a pool, the warm claims no copy."""
    grammar, binding = _pair("warm-owes-nothing")

    with WorkPool(2) as pool:
        replica_module.warm_due(pool, binding)
        claimed = replica_count(grammar, binding)

    assert claimed == 0


def test_another_documents_split_warms_nothing_it_did_not_meet() -> None:
    """Pairs first met through one document's view are not copied for a split
    through another: a one-shot split (a long grammar source in compile_text)
    never has its pairs copied onto every worker for an unrelated parse, and a
    document thread that has gone never has its pairs copied for the next."""
    grammar, binding = _pair("warm-one-shot")
    _other, other_binding = _pair("warm-one-shot-other")

    with WorkPool(2) as pool:
        _pool_views(pool, _Recorder(), threading.Barrier(2), (grammar, binding))
        replica_module.settle_first_meetings(pool, binding)
        replica_module.warm_due(pool.lend(), other_binding)
        claimed = replica_count(grammar, binding)

    assert claimed == 0


def _due_on(pool: WorkPool) -> list[tuple[int, int]]:
    """The due keys naming ``pool``."""
    return [key for key in replica_module.due_census() if key[0] == id(pool)]


def test_a_retired_document_view_takes_its_due_pairs_with_it() -> None:
    """The due list is the document binding's: releasing the binding releases
    it, so a document thread that has gone leaves nothing to warm."""
    grammar, binding = _pair("warm-retires-with-binding")

    with WorkPool(2) as pool:
        _pool_views(pool, _Recorder(), threading.Barrier(2), (grammar, binding))
        replica_module.settle_first_meetings(pool, binding)
        settled = _due_on(pool)
        release((id(binding),))
        assert settled == [(id(pool), id(binding))]
        assert _due_on(pool) == []


def test_a_collected_pool_leaves_no_due_pairs() -> None:
    """A pool closed and dropped — retired, or past the idle cache's limit —
    never splits again, so its due entry goes with it."""
    grammar, binding = _pair("warm-pool-collected")
    pool = WorkPool(2)
    _pool_views(pool, _Recorder(), threading.Barrier(2), (grammar, binding))
    replica_module.settle_first_meetings(pool, binding)
    key = (id(pool), id(binding))
    assert key in replica_module.due_census()
    pool.close()
    del pool
    gc.collect()

    assert key not in replica_module.due_census()


def test_a_piece_the_calling_thread_takes_back_parses_through_its_document_view() -> (
    None
):
    """A piece no worker started, run by the submitting thread, reads that
    thread's own view — the original while no live thread holds it — and
    builds the model a worker would have."""
    grammar, binding = _pair("taken-back-piece")
    gate, started = threading.Event(), threading.Event()
    seen: list[ModelExecutable] = []

    def spy(view_grammar, text, view_binding, config):
        seen.append(view_binding)
        return parse_model(view_grammar, text, view_binding, config)

    def work(item: int) -> IrSelf:
        if item == 0:
            started.set()
            gate.wait(timeout=30)
            return parse_model(grammar, TEXT, binding, DEFAULT_CONFIG)
        try:
            return worker_parse(spy, grammar, TEXT, binding, DEFAULT_CONFIG)
        finally:
            gate.set()

    let_go = threading.Event()
    with WorkPool(3) as pool:
        holder = hold_workers(pool, 2, let_go)
        try:
            held, taken = pool.map(
                work, [0, 1], lambda _submit: started.wait(timeout=30)
            )
        finally:
            let_go.set()
            holder.join(timeout=30)

    assert seen == [binding], "the taken-back piece read the document's view"
    assert taken == held == parse_model(grammar, TEXT, binding, DEFAULT_CONFIG)
