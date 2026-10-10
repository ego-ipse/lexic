"""Per-worker table replicas — why concurrent parses stop fighting each other.

The engine memoises its compiled tables per ``(grammar, binding)`` **identity**,
so every worker parsing one document against one artefact drives the same
table objects. Under free threading that is the bottleneck: the tables are
read-only, but reading them from many cores ping-pongs their reference-count
cache lines, and measured scaling flattens at ~1.8x however many cores exist.

Handing each worker an EQUAL BUT DISTINCT grammar (and its own view of the
binding) gives it its own memo entry, hence its own tables, hence its own cache
lines. Measured on 8 threads: 1.82x shared, 3.71x with grammar replicas alone.
The binding copy adds its own private completion container on top of that;
:meth:`~lexic.parsing.executable.ModelExecutable.replica` is where the depth of that
copy is decided, and the figures measured on a deeper one are not carried here.

**A replica belongs to a THREAD, and to one thread only.** Ownership is
established once, under a lock, the first time a thread asks for a pair; every
later parse reads the answer out of that thread's own thread-local. Neither
half can be an index into a shared list: a pool numbers its own threads, so
two live pools would issue the same numbers against one list, and a length read
followed by an append over-allocates when several threads first-touch a pair at
once.

**A replica's tables are a COPY, not a compile.** A minted view is declared
to the product layer (:func:`~lexic.parsing.products.declare_replica`), and
every product it asks for is the original's, compiled once — whichever thread
asked first — and copied onto the asking thread
(:meth:`~lexic.parsing.executable.ModelExecutable.copied`). An island or a
delegate the copy has not met yet is compiled on the original too and copied
again. So what a grammar compiles is a function of the grammar and the
documents; how many copies exist is not. Replicas are a runtime cache bounded
by the pool: one copy per thread that took a chunk of the pair, released with
that thread, which is a number the scheduler decides.

The models stay identical because the replica is equal by value and holds the
SAME synthesized classes. That sharing is a NECESSITY rather than a compromise
— two workers building two different classes for one rule would break model
equality, which is the thing the split exists to preserve — and it is not what
bounds the scaling: measured on sixteen threads, private classes and shared
ones scale alike (1.33x against 1.27x), so the classes' own refcount traffic is
not where the remaining ceiling sits.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import NamedTuple
from weakref import finalize, ref

from lexic.exceptions import LexicError
from lexic.ir import IrAst
from lexic.parsing.caches import adopt, memo, release
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.policy import available_workers
from lexic.parsing.parallel.pool import WorkPool, running_lease, taking_back
from lexic.parsing.products import declare_replica, model_product

type Replica[M] = tuple[IrAst, ModelExecutable[M]]
"""One worker's private view: an equal grammar, and a binding copy."""


class _Held(NamedTuple):
    """One live thread and the replica it owns until it exits.

    :ivar owner: The claiming thread, held so its liveness can be asked.
    :ivar replica: What that thread parses against for this pair.
    """

    owner: threading.Thread
    replica: Replica


class _Mine[M](NamedTuple):
    """One thread's own replica for a pair, with both key objects pinned.

    Pinned for the reason :class:`_Issued` states: an entry keyed on bare
    ``id`` values can be hit by a brand-new object that landed where a dead one
    used to be, so a hit is only trustworthy while the keys are held.

    :ivar grammar: The key grammar, identity-checked on read.
    :ivar binding: The key binding, likewise.
    :ivar replica: What this thread parses against for that pair.
    :ivar met: The split this thread first met the pair in, while
        :attr:`replica` is still the ORIGINAL pair; ``None`` once the thread
        has earned a copy of its own.
    """

    grammar: IrAst
    binding: ModelExecutable[M]
    replica: Replica[M]
    met: int | None


class _Issued[M](NamedTuple):
    """One artefact pair's replicas, and the key objects they are keyed by.

    The pins are the correctness argument, not a cache. ``id()`` is recycled as
    soon as an address is free, so an entry keyed on bare ints can be HIT by a
    brand-new grammar that merely landed where a dead one used to be — handing
    it a replica compiled for a different grammar entirely.

    :ivar grammar: The key grammar, pinned and identity-checked on read.
    :ivar binding: The key binding, likewise.
    :ivar held: One entry per thread that has claimed a replica for the pair.
    """

    grammar: IrAst
    binding: ModelExecutable[M]
    held: list[_Held]


_REPLICAS: dict[tuple[int, int], _Issued] = memo({}, 0, 1)
"""Replica registry — (id(grammar), id(binding)) → who owns what for that pair."""

_MINTING = threading.Lock()
"""The one synchronised step: claiming a replica for the calling thread.

Cold by construction — a thread claims once per pair and reads its own
thread-local on every parse afterwards, so no lock and no shared lookup is on
the paid path. Without it, N threads first-touching one pair all read the same
old population and mint against it: 16 concurrent requests for 17 replicas
produced 23 to 32 of them.

**Never awaited by a finalizer.** A thread's exit is signalled by a weakref
finalizer (:func:`_arm`), and a finalizer runs on whatever thread the collector
happens to run on — including one that already holds this lock, mid-claim or
mid-release, where releasing a claim frees the very object whose finalizer
retires another thread. A finalizer that waited here waited on itself. So it
only queues (:data:`_RETIRING`), and takes the lock only if it is free; every
holder drains the queue before it lets go (:func:`_minted`).
"""

_RETIRING: deque[threading.Thread] = deque()
"""Exited threads whose claims are still to be released, queued by their
finalizers and drained by whichever thread holds :data:`_MINTING` next."""


# A sentinel has no interface by design: nothing is ever read off it, and its
# only job is to be weakly referenceable, so a finalizer can be armed on an
# object that dies exactly when a thread's own state is freed. The weak
# reference slot is the one thing it must declare — without it the arming
# raises, which is how this was first got wrong.
class _Marker:
    """A per-thread object whose collection IS that thread's exit signal."""

    __slots__ = ("__weakref__",)


_ASSIGNED = threading.local()
"""Each thread's own replica cache, per pair. The cache is what keeps the hot
path a thread-local attribute read — resolving through the shared registry on
every parse would put the lookup itself on the contended path this module
exists to clear, and it measured the difference between 4.1x and 5.6x."""


def _mint[M](
    key: tuple[int, int], grammar: IrAst, binding: ModelExecutable[M], document: bool
) -> Replica[M]:
    """A view of the pair whose compiled tables are this thread's own.

    The BINDING is always copied, and copying it is what makes the view
    private: the instance product is memoised per ``(grammar, binding)``
    identity and mints everything it holds — the lifted grammar, the
    normalised instance, the PDA tables, the collapsed Earley tables — so a
    private binding is a private parse.

    The GRAMMAR is copied for a chunk worker, which also reaches memos keyed
    on the grammar alone, and kept for a document thread, which does not: the
    split plan, the roles, the anchors and every other analysis are memoised
    on it, and replicating it would re-derive all of them per thread to
    privatise nothing that thread parses through.
    """
    view = grammar if document else IrAst(grammar.rules, grammar.start)
    replica = (view, binding.replica())
    declare_replica(grammar, binding, *replica)
    # A minted half exists to get its OWN memo entries — tables, products, run
    # analyses. They live under this entry, so they release with it — under
    # BOTH key identities, because either one retires the entry and neither
    # outlives the other in general. Owned by the grammar alone, a worker's
    # replica outlived the document binding it was minted for and could then
    # be released by nothing short of the artefact.
    minted = tuple(part for part in replica if part is not grammar)
    adopt(key[0], *minted)
    adopt(key[1], *minted)
    return replica


def _reclaim(entry: _Issued) -> None:
    """Drop the claims of threads that have exited, and their memo entries.

    A claim dies with its thread: the thread-local holding it is freed with the
    thread's state, so nothing can still be parsing against that replica. It is
    not re-issued either — its tables were allocated BY the dead thread, and a
    read of another thread's object is exactly the atomic reference count this
    module exists to avoid, so the next worker mints its own and the dead one's
    tables are released rather than kept warm for nobody. What the registry is
    KEYED by is the exception: those two objects outlive every claim, so their
    entries are the artefact's own to release and never a dead claim's.
    """
    _drop(entry, [held for held in entry.held if not held.owner.is_alive()])


def _drop(entry: _Issued, dropped: list[_Held]) -> None:
    """Remove ``dropped`` from ``entry`` and release what they owned.

    One pass over the claims and one place that mutates them, because the two
    callers — the liveness sweep and a thread's own exit — remove different
    claims for the same reason and owe the memos the same thing.
    """
    if not dropped:
        return
    doomed = {id(held) for held in dropped}
    entry.held[:] = [held for held in entry.held if id(held) not in doomed]
    _release_claims(entry, dropped)


def _release_claims(entry: _Issued, dropped: list[_Held]) -> None:
    """Release the memo entries of claims just removed — never the keys.

    The two objects the registry is KEYED by outlive every claim, so they are
    the artefact's own to release and are excluded here however they were
    claimed.

    **Releasing can pop entries from this very registry.** `_REPLICAS` is
    itself a registered memo keyed on both identities, and a second document
    thread's binding replica becomes another entry's KEY — so releasing that
    thread's claim drops that entry. Every caller therefore has to treat the
    registry as changed underneath it afterwards.
    """
    release(
        tuple(
            id(part)
            for held in dropped
            for part in held.replica
            if part is not entry.grammar and part is not entry.binding
        )
    )


def retire_thread(thread: threading.Thread) -> None:
    """Release every replica ``thread`` claimed — its own exit calling in.

    Keyed on the thread OBJECT captured when the worker started, never on
    :func:`threading.current_thread`: this runs while that thread's state is
    being torn down, where the call returns a dummy thread and would match
    nothing.

    It never waits: the thread is queued, and released here only if the lock
    is free — otherwise by the thread holding it, before it lets go.

    This is what makes the release independent of any later parse.
    :func:`_reclaim` prunes only the pair being claimed against, so a pair no
    document touches again keeps its dead claims for the life of the process —
    measured at 189 of 203 claims after one pass over a twelve-grammar roster.

    :param thread: The worker whose claims are to be dropped.
    """
    _RETIRING.append(thread)
    _drain_if_free()


def _retire(thread: threading.Thread) -> None:
    """Drop every claim ``thread`` holds; the caller holds :data:`_MINTING`."""
    # A SNAPSHOT, because releasing a claim can pop entries from the registry
    # being walked: a second document thread's binding replica is another
    # entry's key, and its release drops that entry. Iterating the live view
    # raised `dictionary changed size during iteration` inside the finalizer,
    # where the exception is printed and swallowed — so the loop stopped and
    # every later entry kept this thread's claims, which is the leak
    # `retire_thread` exists to remove.
    for entry in tuple(_REPLICAS.values()):
        _drop(entry, [held for held in entry.held if held.owner is thread])


@contextmanager
def _minted() -> Iterator[None]:
    """Hold :data:`_MINTING` for one synchronised step, and leave it drained."""
    _MINTING.acquire()
    try:
        yield
    finally:
        _release_minting()


def _release_minting() -> None:
    """Retire every thread queued while the lock was held, then release it.

    Asked again once released: a finalizer that queued in between found the
    lock taken and left its thread for the holder. A retirement that queues
    DURING the drain — a released claim freeing another exited thread's
    marker — is picked up by the same loop.
    """
    try:
        while _RETIRING:
            _retire(_RETIRING.popleft())
    finally:
        _MINTING.release()
        # Even when a retirement raised: the rest of the queue is still owed.
        if _RETIRING:
            _drain_if_free()


def _drain_if_free() -> None:
    """Release the queued retirements now, unless another holder will."""
    with _drained_if_free():
        return


@contextmanager
def _drained_if_free() -> Iterator[None]:
    """Hold :data:`_MINTING` only if it is free right now, and leave it
    drained; a lock held elsewhere is drained by its holder before it lets go,
    so this never waits."""
    if not _MINTING.acquire(blocking=False):
        yield
        return
    try:
        yield
    finally:
        _release_minting()


def _arm(thread: threading.Thread) -> None:
    """Arm this thread's exit signal, once, the first time it claims.

    The signal comes from object lifetime, because
    :class:`~concurrent.futures.ThreadPoolExecutor` has an initializer and no
    per-worker exit callback. A bare marker goes into this thread's own local
    state and a finalizer is armed on it: the state is freed when the thread
    ends, the marker is collected, and the finalizer retires what that thread
    held.

    Armed at CLAIM time rather than at worker start, which is both cheaper and
    narrower: a worker that never claims has nothing to release, and a pool
    whose phases never touch the registry pays nothing at all.

    The owning thread is captured here and passed to the finalizer, never read
    inside it. :func:`threading.current_thread` called during a worker's
    teardown returns a dummy thread that matches no claim, so a signal that
    asked who it was at finalization time would retire nothing.
    """
    if getattr(_ASSIGNED, "armed", False):
        return
    marker = _Marker()
    _ASSIGNED.exit = marker
    _ASSIGNED.armed = True
    # Not at interpreter exit: the process is tearing down, every memo goes
    # with it, and a finalizer running then would take the lock and walk the
    # registry to free memory the OS is about to reclaim. `caches.track` sets
    # it the same way for the same reason.
    finalize(marker, retire_thread, thread).atexit = False


def _claim[M](
    key: tuple[int, int],
    grammar: IrAst,
    binding: ModelExecutable[M],
    document: bool,
) -> Replica[M]:
    """Record a view for this thread — the one synchronised step.

    The original pair is a view like any other, and it belongs to the thread
    that owns the DOCUMENT: it is what the submitting thread parses a lead, a
    stand-in shell or a sequential fallback against, so handing it to a chunk
    worker would put that worker on objects the submitting thread allocated. A
    worker therefore always mints; a document thread takes the original when no
    live thread holds it, which also means a single-threaded program compiles
    no second set of tables.
    """
    with _minted():
        entry = _REPLICAS.get(key)
        if entry is None:
            entry = _Issued(grammar, binding, [])
            _REPLICAS[key] = entry
        _reclaim(entry)
        # `_reclaim` releases, releasing can pop, and what it pops may be this
        # entry: re-register before appending, or the claim lands on a list
        # nothing will read again and the replica it records leaks.
        if _REPLICAS.get(key) is not entry:
            _REPLICAS[key] = entry
        spare = not any(held.replica[1] is binding for held in entry.held)
        replica = (
            (grammar, binding)
            if document and spare
            else _mint(key, grammar, binding, document)
        )
        owner = threading.current_thread()
        entry.held.append(_Held(owner, replica))
        _arm(owner)
    return replica


def _resolve[M](
    grammar: IrAst,
    binding: ModelExecutable[M],
    document: bool,
    share_first: bool = True,
) -> Replica[M]:
    """Claim a pair this thread has not cached, and prune what died.

    Off the hot path by construction: a cached pair returns before reaching
    here, so the prune costs a live parse nothing. It bounds the cache by the
    artefacts that still exist — the pinned keys would otherwise make every
    pair this thread ever saw immortal, which is a leak of its own, and this
    cache is the one place with no release path to do it for us. The shared
    registry is keyed identically and IS released, so it is the liveness oracle.
    """
    mine = _thread_cache()
    key = (id(grammar), id(binding))
    for stale in [at for at in mine if at not in _REPLICAS]:
        del mine[stale]
    lease = None if document or not share_first else running_lease()
    if lease is not None and key not in mine:
        # A worker's first split of this pair runs on the original: a copy
        # pays only where the pair is met again — and then all at once, every
        # worker before the next split's pieces (:func:`warm_due`).
        _register(key, grammar, binding)
        mine[key] = _Mine(grammar, binding, (grammar, binding), lease)
        _MET[(lease, *key)] = (grammar, binding)
        return grammar, binding
    replica = _claim(key, grammar, binding, document)
    mine[key] = _Mine(grammar, binding, replica, None)
    return replica


def _register(key: tuple[int, int], grammar: IrAst, binding: ModelExecutable) -> None:
    """Enter the pair in the registry without claiming a copy, so a thread's
    cached first meeting lives exactly as long as the pair does."""
    with _minted():
        if _REPLICAS.get(key) is None:
            _REPLICAS[key] = _Issued(grammar, binding, [])


def _view[M](
    grammar: IrAst,
    binding: ModelExecutable[M],
    document: bool,
    share_first: bool = True,
) -> Replica[M]:
    """This thread's view of the pair — cached, or claimed and then cached.

    ``share_first=False`` asks for this thread's own copy outright: a cached
    first meeting (still the original) does not answer it.
    """
    got = _thread_cache().get((id(grammar), id(binding)))
    # Positional, not by name: this runs once per parse and a NamedTuple's
    # attribute access goes through a descriptor, which measured 87ns dearer
    # per lookup than indexing the same tuple.
    if got is not None and got[0] is grammar and got[1] is binding:
        met = got[3]
        if met is None or (share_first and met == running_lease()):
            return got[2]
    return _resolve(grammar, binding, document, share_first)


def _thread_cache() -> dict[tuple[int, int], _Mine]:
    """The calling thread's own replica cache, made on first use."""
    mine = getattr(_ASSIGNED, "cache", None)
    if mine is None:
        mine = _ASSIGNED.cache = {}
    return mine


_MET: dict[tuple[int, int, int], Replica] = memo({}, 1, 2)
"""``(lease, id(grammar), id(binding))`` → a pair a worker met for the FIRST time
in that split, still read through the original; settled into :data:`_DUE`."""

_DUE: dict[
    tuple[int, int],
    tuple[ref[WorkPool], ModelExecutable, dict[tuple[int, int], Replica]],
] = memo({}, 1)
"""``(id(pool), id(document binding))`` → the pairs that pool's workers met first
while splitting through that binding, due a copy on its next split through it.
Keyed by the binding because every piece parses through it, so the pairs retire
with it and a one-shot split's are never copied for an unrelated one; the pool
is held weakly and its entry goes with it."""

WARM_WAIT = 5.0
"""Seconds a warm task waits for its pool's every worker to ARRIVE (the copy runs
after); past it the barrier breaks, the warm is skipped and counted."""

WARMED, BROKEN, REFUSED = 0, 1, 2
"""How one pair's warm ended: copied everywhere, barrier broken, or refused."""


class _WarmTally:
    """Every warm's outcome so far, so a broken barrier is never silent."""

    __slots__ = ("counts", "lock")

    def __init__(self) -> None:
        """Start every outcome at zero."""
        self.counts, self.lock = [0, 0, 0], threading.Lock()

    def add(self, outcome: int) -> None:
        """Count one pair's warm."""
        with self.lock:
            self.counts[outcome] += 1

    def census(self) -> tuple[int, int, int]:
        """``(warmed, broken, refused)`` so far."""
        with self.lock:
            return self.counts[WARMED], self.counts[BROKEN], self.counts[REFUSED]


_TALLY = _WarmTally()


def settle_first_meetings(pool: WorkPool, document: ModelExecutable) -> None:
    """At a split's end, its workers' first meetings become due on ``pool``.

    :param pool: The pool the split ran on.
    :param document: The split document's executable view.
    """
    # A snapshot: other pools' workers file into the same memo meanwhile.
    met = [key for key in _MET.copy() if key[0] == pool.lease]
    pairs = {key[1:]: pair for key in met if (pair := _MET.pop(key, None)) is not None}
    key = (id(pool), id(document))
    if pool.retired:
        _DUE.pop(key, None)
        return
    if not pairs:
        return
    entry = _DUE.get(key)
    if entry is None or entry[0]() is not pool or entry[1] is not document:
        entry = _DUE[key] = (ref(pool, partial(_forget, key)), document, {})
    entry[2].update(pairs)


def _forget(key: tuple[int, int], gone: ref[WorkPool]) -> None:
    """A collected pool's due entry goes with it, unless ``key`` was reused."""
    entry = _DUE.get(key)
    if entry is not None and entry[0] is gone:
        _DUE.pop(key, None)


def warm_due(pool: WorkPool, document: ModelExecutable) -> None:
    """At a split's start, every worker of ``pool`` copies each pair due for
    ``document``: one task per worker per pair behind a barrier, so each thread
    copies once, in parallel, and never inside a piece. A refusing copy ends
    the warm; anything else is a bug and leaves as :meth:`WorkPool.map`'s do.

    :param pool: The pool about to split a document.
    :param document: That document's executable view.
    """
    entry = _DUE.pop((id(pool), id(document)), None)
    if (
        entry is None
        or entry[0]() is not pool
        or entry[1] is not document
        or pool.retired
    ):
        return
    for grammar, binding in entry[2].values():
        arrive = threading.Barrier(pool.workers, timeout=WARM_WAIT)
        try:
            pool.map(
                partial(_warm, grammar, binding, arrive), list(range(pool.workers))
            )
        except LexicError:  # an optimisation never decides the parse
            _TALLY.add(REFUSED)
            return
        _TALLY.add(BROKEN if arrive.broken else WARMED)


def _warm(
    grammar: IrAst, binding: ModelExecutable, arrive: threading.Barrier, _slot: int
) -> None:
    """One worker's copy of the pair, its product at the tier every piece under
    2**28 characters parses at, and every island the original has met."""
    try:
        arrive.wait()
    except threading.BrokenBarrierError:
        return
    view_grammar, view_binding = _view(grammar, binding, False, share_first=False)
    model_product(view_grammar, view_binding, tier_for(0)).pda.copy_held_islands()


def warm_census() -> tuple[int, int, int]:
    """``(warmed, broken, refused)`` warms, process-wide."""
    return _TALLY.census()


def due_census() -> tuple[tuple[int, int], ...]:
    """Every ``(id(pool), id(document binding))`` a warm is still owed for."""
    return tuple(_DUE.copy())


def worker_replica[M](grammar: IrAst, binding: ModelExecutable[M]) -> Replica[M]:
    """The CALLING worker thread's own view of ``(grammar, binding)``.

    Held for the thread's whole life, so a worker parsing chunk after chunk
    stays on the objects it compiled. A replica's tables are built by whichever
    thread first parses against it, and under free threading every later read
    of those objects from a different thread is an atomic reference count
    instead of a local one: pairing a chunk with the replica at its TASK number
    put 44% (cut route) to 74% (region route) of chunk parses on some other
    thread's replica, and such a parse costs 12 to 23% more CPU.

    :param grammar: The codegen grammar this thread parses against.
    :param binding: The bound product that grammar was compiled with.
    :returns: This thread's replica — never the original pair, which belongs
        to the thread that submitted the work.
    """
    return _view(grammar, binding, False)


def document_view[M](grammar: IrAst, binding: ModelExecutable[M]) -> ModelExecutable[M]:
    """A whole-document parse's own EXECUTABLE view of the pair.

    Claimed before any split work and held for the whole of it. A split's
    driver thread does not only hand chunks out: it parses the separator
    leads, the routed stand-in shell, the region boundaries, and the
    sequential fallback, and it stitches through this product afterwards. All
    of that must run on a view no other whole-document caller can be handed.

    The executable half ONLY, because that is the half that privatises a
    parse — see :func:`_mint`. The grammar stays the artefact's, so the split
    plan and every analysis keyed on it are still derived once for the
    process rather than once per thread.

    The FIRST document thread keeps the original product: it is the submitting
    thread's, and a program parsing on one thread must not compile a second
    set of tables to say so. GIL builds and sequential callers get it without
    claiming anything.

    :param grammar: The codegen grammar, which is also the plan's identity.
    :param binding: The bound model product.
    :returns: The calling thread's executable view of it.
    """
    if available_workers() < 2:
        return binding
    return _view(grammar, binding, True)[1]


def worker_parse[M](
    parse: ModelParse[M],
    grammar: IrAst,
    text: str,
    binding: ModelExecutable[M],
    config: ParseConfig,
) -> M:
    """Parse ``text`` against the CALLING worker thread's own view of ``grammar``.

    **Call it from inside the work.** The view belongs to the thread, not to
    the task, so no worker ever reads objects the submitting thread allocated;
    an item the submitting thread takes back reads that thread's own view.

    :param parse: The model product, injected by the caller.
    :param grammar: The grammar this chunk is parsed against.
    :param text: This worker's chunk, not the whole document.
    :param binding: The bound product producing ``M``.
    :param config: The caller's resolver and split decider.
    :returns: The chunk's model.
    """
    view_grammar, view_binding = _view(grammar, binding, taking_back())
    return parse(view_grammar, text, view_binding, config)


def claim_census() -> tuple[int, int]:
    """Claims across the whole registry, split by whether their thread lives.

    The sibling of :func:`replica_count`, which meters one pair. This one
    answers the lifetime question the pair-wise meter cannot: whether anything
    is held by a thread that has already exited. A non-zero second element
    means a claim outlived its owner and nothing released it.

    :returns: ``(live, dead)`` claim counts.
    """
    with _minted():
        owners = [held.owner for entry in _REPLICAS.values() for held in entry.held]
    live = sum(owner.is_alive() for owner in owners)
    return live, len(owners) - live


def replica_count(grammar: IrAst, binding: ModelExecutable) -> int:
    """How many replicas a pair has issued — the ownership probe's meter.

    :param grammar: The key grammar.
    :param binding: The key binding.
    :returns: One per claiming thread, live or exited but not yet reclaimed.
    """
    entry = _REPLICAS.get((id(grammar), id(binding)))
    return 0 if entry is None else len(entry.held)
