"""Per-worker table replicas — why concurrent parses stop fighting each other.

The engine memoises its compiled tables per ``(grammar, fold)`` **identity**,
so every worker parsing one document against one artefact drives the same
table objects. Under free threading that is the bottleneck: the tables are
read-only, but reading them from many cores ping-pongs their reference-count
cache lines, and measured scaling flattens at ~1.8x however many cores exist.

Handing each worker an EQUAL BUT DISTINCT grammar (and its own view of the
fold) gives it its own memo entry, hence its own tables, hence its own cache
lines. Measured on 8 threads: 1.82x shared, 3.71x with grammar replicas,
4.21x with the fold copied too.

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

_REPLICAS: dict[tuple[int, int], tuple[IrAst, ModelFold, list[Replica]]] = {}
"""Replica memo — (id(grammar), id(fold)) → (grammar, fold, replicas). The
strong references pin both ids, so a recycled id cannot alias a live entry."""


def replicas[M](grammar: IrAst, fold: ModelFold[M], count: int) -> list[Replica]:
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
        pool.append((IrAst(grammar.rules, grammar.start), copy.copy(fold)))
    return pool[:count]


_ASSIGNED = threading.local()
"""Each thread's replica index — assigned once and then stable, because a
thread that changed tables between parses would pay the very cache-line
cost this module exists to avoid. One index serves every grammar: the
replica lists are per pair, and a thread wants the same SLOT in each."""

_TICKET = itertools.count()
"""Hands out replica indices round-robin as threads first ask."""


def thread_replica[M](grammar: IrAst, fold: ModelFold[M]) -> Replica:
    """This thread's private view of ``(grammar, fold)`` — its own tables.

    The document-level twin of :func:`replicas`: where a split hands each
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
    mine = getattr(_ASSIGNED, "index", None)
    if mine is None:
        mine = _ASSIGNED.index = next(_TICKET)
    return replicas(grammar, fold, workers)[mine % workers]
