"""Identity memos under concurrent claim, release and collection.

``caches.py`` mutates three plain containers from whatever thread dropped the
last reference to an artefact: each registered memo dict, ``_ADOPTED``
(``setdefault(...).update(...)`` against ``pop(...)``) and ``_CLAIMED``
(``update`` against ``difference_update``). On a free-threaded build those are
genuine races, and they fail in three ways: an exception out of the sweep
(``RuntimeError: dictionary changed size during iteration``, a ``KeyError``
from a double pop), a lost adoption edge stranding an entry that should have
been released, and — the quiet one — a stale ``_CLAIMED`` identity, which
matters because ``id()`` is reused after collection, so a claim left behind
makes a LATER object's ``track()`` a silent no-op.

The artefacts churned here are built the way :meth:`CompiledGrammar.bind`
builds one: a fresh codegen-grammar identity over reused classes, binding and
fold. That is deliberate. ``compile_text`` memoises its result, so an artefact
obtained through it is pinned for the life of the process and can never be
observed to release; the rebind path is the one ``caches.py``'s own docstring
names as the reason the ownership machinery exists.

**What a green run here means.** The exactness tests bound a failure rate
rather than excluding it — a lost update under a real race is probabilistic,
and rounds and thread count are what raise detection, not what certify
absence. The population test below is the exception: its defect turned out to
be deterministic in the number of threads (it needs only that the churn is off
the main thread), so that one either fires or the bug is gone.
"""

from __future__ import annotations

import gc
import threading
from collections.abc import Callable
from functools import partial

from lexic.compile import CompiledGrammar, compile_text
from lexic.compile.pipeline.moments import CompileMoments, GrammarMoments
from lexic.ir import IrAst
from lexic.parsing.caches import _CLAIMED, cached_entries, memo, release, track
from tests.integration.lexic.concurrency.concurrency import clean, parallel
from tests.integration.lexic.concurrency.fixtures import FLAT, flat_doc

ROUNDS = 40
"""Iterations per worker — bounded so the lane stays quick, and large enough
that a lost update gets many chances to show."""

WAVES = 4
"""Churn waves the leak probe runs. The residue accumulates per wave, and
the growth is what distinguishes a leak from a first-parse cost."""

PARSERS = 4
CHURNERS = 4


def _owner() -> threading.Event:
    """A distinct, weak-referenceable stand-in for an artefact.

    ``threading.Event`` is what the unit tests beside ``caches.py`` already
    use for this: cheap, weak-referenceable, and distinct per call.
    """
    return threading.Event()


def _variant(base: CompiledGrammar) -> CompiledGrammar:
    """A fresh artefact over ``base``'s classes — a rebind without a vocabulary.

    Only the codegen grammar's identity is new, which is what
    :meth:`CompiledGrammar.bind` changes and what the identity memos key on.
    Unlike a ``compile_text`` result it is unmemoised, so dropping the last
    reference really does end its life.
    """
    moments = base.moments.grammar
    return CompiledGrammar(
        grammar=base.grammar,
        fold=base.fold,
        moments=CompileMoments(
            GrammarMoments(*moments[:-1], resolved=IrAst(*moments.resolved)),
            base.moments.binding,
            base.moments.classes,
        ),
        flavour=base.flavour,
        stem=base.stem,
    )


def _quiesce() -> None:
    """Run every pending finalizer before reading a population."""
    gc.collect()
    gc.collect()


def _dispatch(index: int, workers: list[Callable[[int], int]]) -> int:
    """Run the worker assigned to this index — a heterogeneous race."""
    return workers[index](index)


def _parse_repeatedly(index: int, base: CompiledGrammar, text: str) -> int:
    """Read the memos hard while the other workers churn them."""
    del index
    for _ in range(ROUNDS):
        assert base.parse(text).to_text() == text
    return ROUNDS


def _churn_artefacts(index: int, base: CompiledGrammar, text: str) -> int:
    """Mint an artefact, use it, drop it; report the memo peak it caused.

    Sampling here rather than from a separate poller is what makes the peak
    mean something: it is read while this worker's own artefact is alive, so a
    reading above the floor is proof the churn and the parses really overlapped.
    """
    del index
    peak = 0
    for _ in range(ROUNDS):
        variant = _variant(base)
        assert variant.parse(text).to_text() == text
        peak = max(peak, cached_entries())
        del variant
        gc.collect()
    return peak


def _churn_claims(index: int, entries: dict[tuple[int, str], str]) -> int:
    """Track owners with adopted chains, then release them by hand."""
    for round_at in range(ROUNDS):
        owner = _owner()
        derived = _owner()
        entries[(id(owner), f"{index}-{round_at}")] = "owned"
        entries[(id(derived), f"{index}-{round_at}-derived")] = "adopted"
        track(owner, owner, derived)
        release((id(owner), id(derived)))
    return ROUNDS


def _insert_repeatedly(index: int, entries: dict[tuple[int, str], str]) -> int:
    """Write into and delete from the memo a releaser is sweeping."""
    del index
    marker = _owner()
    for round_at in range(ROUNDS * 10):
        entries[(id(marker), f"writer-{round_at}")] = "live"
        entries.pop((id(marker), f"writer-{round_at}"), None)
    return ROUNDS


def test_artefact_churn_under_concurrent_parses_stays_exact() -> None:
    """Artefacts created and dropped while parses read the same memos.

    The claim here is about ANSWERS, not populations: an entry evicted while a
    parse is deriving through it must cost a recomputation and change nothing,
    because every registered memo is documented as a pure memo. The population
    question needs a different shape and is asked separately below.
    """
    base = compile_text(FLAT, cache_key="concurrency-caches")
    text = flat_doc(0, 60)
    workers: list[Callable[[int], int]] = [
        partial(_parse_repeatedly, base=base, text=text)
    ] * PARSERS
    workers += [partial(_churn_artefacts, base=base, text=text)] * CHURNERS

    counts = clean(parallel(partial(_dispatch, workers=workers), len(workers)))
    assert counts[:PARSERS] == [ROUNDS] * PARSERS
    assert min(counts[PARSERS:]) > 0, "no churn was ever live — nothing raced"


def test_artefact_churn_off_the_main_thread_returns_memos_to_the_floor() -> None:
    """Churn alone, wave after wave: the population must not drift upward.

    One worker thread, deliberately, and off the MAIN thread — that pairing
    is what used to leak, because a brand-new grammar landing on a recycled
    address hit the per-thread replica cache and was handed another
    grammar's replica, rooting its whole derivation under an identity it did
    not own. Parser threads are kept out because a live artefact's own
    per-thread entries legitimately accrue and would muddy the reading.
    """
    base = compile_text(FLAT, cache_key="concurrency-caches")
    text = flat_doc(0, 60)
    churn = partial(_churn_artefacts, base=base, text=text)

    readings = []
    for _ in range(WAVES):
        clean(parallel(churn, 1), least=1)  # one thread: overlap is not the point
        _quiesce()
        readings.append(cached_entries())
    assert readings[-1] <= readings[0], f"memo population drifted up: {readings}"


def test_release_survives_a_real_concurrent_writer_on_the_same_memo() -> None:
    """The seed's simulated pop, run for real: sweeps and writes interleaved.

    ``release`` sweeps a private copy and deletes with ``pop``, so a key
    vanishing or appearing mid-sweep is tolerated rather than raised. The unit
    test pins that shape with one hand-made pop; this races an actual writer
    against an actual sweep.
    """
    entries: dict[tuple[int, str], str] = memo({}, 0)
    workers: list[Callable[[int], int]] = [partial(_churn_claims, entries=entries)] * 3
    workers += [partial(_insert_repeatedly, entries=entries)] * 3
    clean(parallel(partial(_dispatch, workers=workers), len(workers)))
    _quiesce()
    assert not entries, f"the sweep left {len(entries)} entries behind"


def test_concurrent_track_and_release_drains_every_claim() -> None:
    """``_CLAIMED`` returns to its floor, so no identity stays spoken for.

    A stale claim is the failure that hides: ``id()`` is reused, so a claim
    outliving its owner silently disarms the NEXT artefact's ``track()``.
    Counting rather than naming ids avoids the false positive an id reuse
    would otherwise cause.
    """
    entries: dict[tuple[int, str], str] = memo({}, 0)
    _quiesce()
    floor = len(_CLAIMED)
    clean(parallel(partial(_churn_claims, entries=entries), 8))
    _quiesce()
    assert len(_CLAIMED) == floor, "claims outlived the owners that made them"
    assert not entries, "released owners left memo entries behind"
