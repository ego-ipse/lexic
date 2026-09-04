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

The models stay identical because the replica is equal by value and holds the
SAME synthesized classes — which is also the ceiling here. The classes are
shared by necessity (two workers building two different classes for one rule
would break model equality, the thing the split exists to preserve), so their
own refcount traffic remains.
"""

from __future__ import annotations

import threading
from typing import NamedTuple

from lexic.ir import IrAst
from lexic.parsing.caches import adopt, memo, release
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.executable import ModelExecutable, ModelParse
from lexic.parsing.parallel.policy import available_workers

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
    """

    grammar: IrAst
    binding: ModelExecutable[M]
    replica: Replica[M]


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
"""

_ASSIGNED = threading.local()
"""Each thread's own replica cache, per pair. The cache is what keeps the hot
path a thread-local attribute read — resolving through the shared registry on
every parse would put the lookup itself on the contended path this module
exists to clear, and it measured the difference between 4.1x and 5.6x."""


def _mint[M](owner: int, grammar: IrAst, binding: ModelExecutable[M]) -> Replica[M]:
    """An equal-but-distinct view of the pair, adopted under the key grammar."""
    replica = (IrAst(grammar.rules, grammar.start), binding.replica())
    # A replica exists to get its OWN memo entries — tables, products, run
    # analyses. They live under this entry, so they release with it.
    adopt(owner, *replica)
    return replica


def _reclaim(entry: _Issued) -> None:
    """Drop the claims of threads that have exited, and their memo entries.

    A claim dies with its thread: the thread-local holding it is freed with the
    thread's state, so nothing can still be parsing against that replica. It is
    not re-issued either — its tables were allocated BY the dead thread, and a
    read of another thread's object is exactly the atomic reference count this
    module exists to avoid, so the next worker mints its own and the dead one's
    tables are released rather than kept warm for nobody. The original pair is
    the exception the registry is KEYED by: it outlives every claim, so its
    entries are the artefact's own to release.
    """
    alive = [held for held in entry.held if held.owner.is_alive()]
    if len(alive) == len(entry.held):
        return
    gone = tuple(
        id(part)
        for held in entry.held
        if not held.owner.is_alive() and held.replica[0] is not entry.grammar
        for part in held.replica
    )
    entry.held[:] = alive
    release(gone)


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
    with _MINTING:
        entry = _REPLICAS.get(key)
        if entry is None:
            entry = _Issued(grammar, binding, [])
            _REPLICAS[key] = entry
        _reclaim(entry)
        spare = not any(held.replica[0] is grammar for held in entry.held)
        replica = (
            (grammar, binding)
            if document and spare
            else _mint(key[0], grammar, binding)
        )
        entry.held.append(_Held(threading.current_thread(), replica))
    return replica


def _resolve[M](
    mine: dict[tuple[int, int], _Mine],
    key: tuple[int, int],
    grammar: IrAst,
    binding: ModelExecutable[M],
    document: bool,
) -> Replica[M]:
    """Claim a pair this thread has not cached, and prune what died.

    Off the hot path by construction: a cached pair returns before reaching
    here, so the prune costs a live parse nothing. It bounds the cache by the
    artefacts that still exist — the pinned keys would otherwise make every
    pair this thread ever saw immortal, which is a leak of its own, and this
    cache is the one place with no release path to do it for us. The shared
    registry is keyed identically and IS released, so it is the liveness oracle.
    """
    for stale in [at for at in mine if at not in _REPLICAS]:
        del mine[stale]
    replica = _claim(key, grammar, binding, document)
    mine[key] = _Mine(grammar, binding, replica)
    return replica


def _view[M](grammar: IrAst, binding: ModelExecutable[M], document: bool) -> Replica[M]:
    """This thread's view of the pair — cached, or claimed and then cached."""
    mine = getattr(_ASSIGNED, "cache", None)
    if mine is None:
        mine = _ASSIGNED.cache = {}
    key = (id(grammar), id(binding))
    got = mine.get(key)
    # Positional, not by name: this runs once per parse and a NamedTuple's
    # attribute access goes through a descriptor, which measured 87ns dearer
    # per lookup than indexing the same tuple.
    if got is not None and got[0] is grammar and got[1] is binding:
        return got[2]
    return _resolve(mine, key, grammar, binding, document)


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


def thread_replica[M](grammar: IrAst, binding: ModelExecutable[M]) -> Replica[M]:
    """A whole-document parse's view of the pair, replicated when it pays.

    Concurrent whole-document parses contend on one artefact's tables exactly
    as chunk workers do, so a second such thread parses against its own. The
    FIRST keeps the original pair — it is the submitting thread's, and a
    program parsing on one thread must not compile a second set of tables to
    say so. GIL builds and sequential callers get it without claiming anything.

    :param grammar: The codegen grammar.
    :param binding: The bound model product.
    :returns: The calling thread's view.
    """
    if available_workers() < 2:
        return (grammar, binding)
    return _view(grammar, binding, True)


def worker_parse[M](
    parse: ModelParse[M],
    grammar: IrAst,
    text: str,
    binding: ModelExecutable[M],
    resolve: Resolver | None,
) -> M:
    """Parse ``text`` against the CALLING worker thread's own view of ``grammar``.

    **Call it from inside the work, never from the submitting thread.** The
    view belongs to the thread, not to the task, and the submitting thread has
    its own — so no worker ever reads objects that thread allocated.

    :param parse: The model product, injected by the caller.
    :param grammar: The grammar this chunk is parsed against.
    :param text: This worker's chunk, not the whole document.
    :param binding: The bound product producing ``M``.
    :param resolve: The caller's ambiguity resolver, or ``None``.
    :returns: The chunk's model.
    """
    view_grammar, view_binding = worker_replica(grammar, binding)
    return parse(view_grammar, text, view_binding, resolve)


def replica_count(grammar: IrAst, binding: ModelExecutable) -> int:
    """How many replicas a pair has issued — the ownership probe's meter.

    :param grammar: The key grammar.
    :param binding: The key binding.
    :returns: One per claiming thread, live or exited but not yet reclaimed.
    """
    entry = _REPLICAS.get((id(grammar), id(binding)))
    return 0 if entry is None else len(entry.held)
