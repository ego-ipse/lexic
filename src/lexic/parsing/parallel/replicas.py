"""Per-worker table replicas — why concurrent parses stop fighting each other.

The engine memoises its compiled tables per ``(grammar, binding)`` **identity**,
so every worker parsing one document against one artefact drives the same
table objects. Under free threading that is the bottleneck: the tables are
read-only, but reading them from many cores ping-pongs their reference-count
cache lines, and measured scaling flattens at ~1.8x however many cores exist.

Handing each worker an EQUAL BUT DISTINCT grammar (and its own view of the
binding) gives it its own memo entry, hence its own tables, hence its own cache
lines. Measured on 8 threads: 1.82x shared, 3.71x with grammar replicas, 4.21x
with the fold shallow-copied, 5.34x once the fold's container spine is
copied too (:func:`_replicate` — deepcopy cannot be used, and a shallow
copy leaves every table shared).

The models stay identical because the replica is equal by value and the fold
copy holds the SAME synthesized classes — which is also the ceiling here.
The classes are shared by necessity (two workers building two different
classes for one rule would break model equality, the thing the split exists
to preserve), so their own refcount traffic remains, and ~4.2x rather than
the ~6.5x of fully separate artefacts is what this buys.
"""

from __future__ import annotations

import itertools
import threading
from typing import NamedTuple

from lexic.ir import IrAst
from lexic.parsing.binding import ModelBinding
from lexic.parsing.caches import adopt, memo
from lexic.parsing.parallel.policy import available_workers

Replica = tuple[IrAst, ModelBinding]
"""One worker's private view: an equal grammar, and a binding copy."""


def _binding_copy[M](binding: ModelBinding[M]) -> ModelBinding[M]:
    """A binding whose rule map is this worker's own.

    The memo keys on the BINDING's identity, so the copy has to be of the
    binding; the rule map is rebuilt inside because it is the container every
    completion reads, and therefore the one whose sharing costs the refcount
    traffic — the same container graph, and the same measured 8-thread
    scaling move from 4.21x to 5.34x, that copying the fold's config bought.

    What it holds is deliberately NOT copied. The rule products and the
    construction tables are immutable records, and a worker rebuilding them
    would change what a model is built from; model equality across workers is
    the contract the whole split rests on. Constructing the binding over the
    private map is also what gives each worker its own executor, without a
    second place deciding that.
    """
    return ModelBinding(dict(binding.rules), binding.owned)


_REPLICAS: dict[tuple[int, int], tuple[IrAst, ModelBinding, list[Replica]]] = memo(
    {}, 0, 1
)
"""Replica memo — (id(grammar), id(binding)) → (grammar, binding, replicas). The
strong references pin both ids, so a recycled id cannot alias a live entry."""


def worker_replicas[M](
    grammar: IrAst, binding: ModelBinding[M], count: int
) -> list[Replica]:
    """``count`` private ``(grammar, binding)`` views, grown and reused per pair.

    Replicas are built once per pair and kept: each carries its own compiled
    tables, so discarding them would pay the compile again on the next parse.
    Growing an existing list keeps the already-warm replicas warm.

    :param grammar: The codegen grammar workers parse against.
    :param binding: The bound product that grammar was compiled with.
    :param count: How many workers need a view.
    :returns: Exactly ``count`` replicas; the first is the original pair, so
        a single worker costs nothing.
    """
    key = (id(grammar), id(binding))
    entry = _REPLICAS.get(key)
    if entry is None:
        entry = (grammar, binding, [(grammar, binding)])
        _REPLICAS[key] = entry
    pool = entry[2]
    while len(pool) < count:
        replica = (IrAst(grammar.rules, grammar.start), _binding_copy(binding))
        # A replica exists to get its OWN memo entries — tables, products,
        # run analyses. They live inside this pool, so they release with it.
        adopt(key[0], *replica)
        pool.append(replica)
    return pool[:count]


class _Assigned(NamedTuple):
    """One thread's resolved replica, with both key objects pinned.

    The pins are the correctness argument, not a cache. ``id()`` is recycled
    as soon as an address is free, so an entry keyed on bare ints can be HIT
    by a brand-new grammar that merely landed where a dead one used to be —
    handing it a replica compiled for a different grammar entirely. Holding
    the key objects means an address cannot be recycled while it is cached,
    so a hit is always the right pair. This is the same argument
    :data:`_REPLICAS` states one function above; only this cache lacked it.

    :ivar grammar: The key grammar, pinned and identity-checked on read.
    :ivar binding: The key binding, likewise.
    :ivar replica: What this thread parses against for that pair.
    """

    grammar: IrAst
    binding: ModelBinding
    replica: Replica


_ASSIGNED = threading.local()
"""Each thread's own replica cache: its slot index, and the replica it
resolved per pair. The cache is what keeps the hot path a thread-local
attribute read — resolving through the shared memo on every parse would
put the lookup itself on the contended path this module exists to clear,
and it measured the difference between 4.1x and 5.6x."""

_TICKET = itertools.count()
"""Hands out replica indices round-robin as threads first ask."""


def _resolve[M](
    mine: dict[tuple[int, int], _Assigned],
    key: tuple[int, int],
    grammar: IrAst,
    binding: ModelBinding[M],
    workers: int,
) -> Replica:
    """Resolve a pair this thread has not cached, and prune what died.

    Off the hot path by construction: a cached pair returns before reaching
    here, so the prune costs a live parse nothing. It bounds the cache by the
    artefacts that still exist — the pinned keys would otherwise make every
    pair this thread ever saw immortal, which is a leak of its own, and this
    cache is the one place with no release path to do it for us. The shared
    memo is keyed identically and IS released, so it is the liveness oracle.
    """
    for stale in [at for at in mine if at not in _REPLICAS]:
        del mine[stale]
    pool = worker_replicas(grammar, binding, workers)
    replica = pool[_ASSIGNED.index % workers]
    mine[key] = _Assigned(grammar, binding, replica)
    return replica


def thread_replica[M](grammar: IrAst, binding: ModelBinding[M]) -> Replica:
    """This thread's private view of ``(grammar, binding)`` — its own tables.

    The document-level twin of :func:`worker_replicas`: where a split hands each
    CHUNK a view, concurrent whole-document parses need each THREAD to have
    one, and to keep it. Sequential callers and GIL builds get the original
    pair back, so nothing is compiled or held that could not be used.

    :param grammar: The codegen grammar.
    :param binding: The bound model product.
    :returns: The calling thread's replica.
    """
    workers = available_workers()
    if workers < 2:
        return (grammar, binding)
    mine = getattr(_ASSIGNED, "cache", None)
    if mine is None:
        mine = _ASSIGNED.cache = {}
        _ASSIGNED.index = next(_TICKET)
    key = (id(grammar), id(binding))
    got = mine.get(key)
    # Positional, not by name: this runs once per parse and a NamedTuple's
    # attribute access goes through a descriptor, which measured 87ns dearer
    # per lookup than indexing the same tuple.
    if got is not None and got[0] is grammar and got[1] is binding:
        return got[2]
    return _resolve(mine, key, grammar, binding, workers)
