"""Per-worker table replicas — why concurrent parses stop fighting each other.

The engine memoises its compiled tables per ``(grammar, fold)`` **identity**,
so every worker parsing one document against one artefact drives the same
table objects. Under free threading that is the bottleneck: the tables are
read-only, but reading them from many cores ping-pongs their reference-count
cache lines, and measured scaling flattens at ~1.8x however many cores exist.

Handing each worker an EQUAL BUT DISTINCT grammar (and its own view of the
fold) gives it its own memo entry, hence its own tables, hence its own cache
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

import copy
import itertools
import threading

from lexic.ir import IrAst
from lexic.parsing.fold import ModelFold
from lexic.parsing.parallel.policy import available_workers

Replica = tuple[IrAst, ModelFold]
"""One worker's private view: an equal grammar, and a fold copy."""

_MAX_DEPTH = 6
"""How deep a fold's container graph is rebuilt. Past this the sharing costs
less than the walk; measured, the win is all in the first few levels."""


def _replicate(value: object, depth: int = 0) -> object:
    """A private copy of ``value``'s plain containers; everything else shared.

    ``copy.deepcopy`` cannot be used — a fold holds ``IrLambda`` bodies that
    refuse reconstruction — and a shallow copy leaves every table shared,
    which is most of what workers contend on. Rebuilding the plain
    ``dict``/``list``/``tuple`` spine is the part that CAN be copied, and
    measured it moved 8-thread scaling from 4.21x to 5.34x.

    Exact types only, so IR nodes (tuple SUBCLASSES) and synthesized model
    classes stay shared: copying those would change what a model IS, and
    model equality across workers is the contract the whole split rests on.
    """
    if depth > _MAX_DEPTH:
        return value
    kind = type(value)
    if kind is dict:
        assert isinstance(value, dict)
        return {k: _replicate(v, depth + 1) for k, v in value.items()}
    if kind is list:
        assert isinstance(value, list)
        return [_replicate(v, depth + 1) for v in value]
    if kind is tuple:
        assert isinstance(value, tuple)
        return tuple(_replicate(v, depth + 1) for v in value)
    return value


def _fold_copy[M](fold: ModelFold[M]) -> ModelFold[M]:
    """A fold whose container spine is this worker's own."""
    out = copy.copy(fold)
    names = [
        slot for cls in type(fold).__mro__ for slot in getattr(cls, "__slots__", ())
    ]
    names += list(vars(out)) if hasattr(out, "__dict__") else []
    for name in names:
        try:
            setattr(out, name, _replicate(getattr(out, name)))
        except AttributeError, TypeError:
            continue  # read-only or absent: sharing it is always correct
    return out


_REPLICAS: dict[tuple[int, int], tuple[IrAst, ModelFold, list[Replica]]] = {}
"""Replica memo — (id(grammar), id(fold)) → (grammar, fold, replicas). The
strong references pin both ids, so a recycled id cannot alias a live entry."""


def worker_replicas[M](grammar: IrAst, fold: ModelFold[M], count: int) -> list[Replica]:
    """``count`` private ``(grammar, fold)`` views, grown and reused per pair.

    Replicas are built once per pair and kept: each carries its own compiled
    tables, so discarding them would pay the compile again on the next parse.
    Growing an existing list keeps the already-warm replicas warm.

    :param grammar: The codegen grammar workers parse against.
    :param fold: The instance fold that grammar was compiled with.
    :param count: How many workers need a view.
    :returns: Exactly ``count`` replicas; the first is the original pair, so
        a single worker costs nothing.
    """
    key = (id(grammar), id(fold))
    entry = _REPLICAS.get(key)
    if entry is None:
        entry = (grammar, fold, [(grammar, fold)])
        _REPLICAS[key] = entry
    pool = entry[2]
    while len(pool) < count:
        pool.append((IrAst(grammar.rules, grammar.start), _fold_copy(fold)))
    return pool[:count]


_ASSIGNED = threading.local()
"""Each thread's own replica cache: its slot index, and the replica it
resolved per pair. The cache is what keeps the hot path a thread-local
attribute read — resolving through the shared memo on every parse would
put the lookup itself on the contended path this module exists to clear,
and it measured the difference between 4.1x and 5.6x."""

_TICKET = itertools.count()
"""Hands out replica indices round-robin as threads first ask."""


def thread_replica[M](grammar: IrAst, fold: ModelFold[M]) -> Replica:
    """This thread's private view of ``(grammar, fold)`` — its own tables.

    The document-level twin of :func:`worker_replicas`: where a split hands each
    CHUNK a view, concurrent whole-document parses need each THREAD to have
    one, and to keep it. Sequential callers and GIL builds get the original
    pair back, so nothing is compiled or held that could not be used.

    :param grammar: The codegen grammar.
    :param fold: The instance fold.
    :returns: The calling thread's replica.
    """
    workers = available_workers()
    if workers < 2:
        return (grammar, fold)
    mine = getattr(_ASSIGNED, "cache", None)
    if mine is None:
        mine = _ASSIGNED.cache = {}
        _ASSIGNED.index = next(_TICKET)
    key = (id(grammar), id(fold))
    got = mine.get(key)
    if got is None:
        pool = worker_replicas(grammar, fold, workers)
        got = mine[key] = pool[_ASSIGNED.index % workers]
    return got
