"""What a split attempt DID, as against what it was asked for.

The request is not an observation. Production clamps useful workers by document
size and cut count, cut selection can clamp them again, and the executor only
starts the threads its submitted tasks demand — so a row that reports the
number it asked for certifies nothing, and two arms echoing the same request
can divide one document differently and still compare.

**Two different questions come out of one attempt, and they must not be
confused.** What the split DECIDED to do — how it carved the document, and how
many workers that carving admits — is derived from the grammar, the document
and the core request, and is identical on every attempt. How many threads
happened to pick the pieces up is the executor's business: thirty identical
attempts on one artefact read eight workers twenty-eight times and seven twice.
The first is workload identity and belongs in the comparison; the second is
diagnostic evidence and would reject a pair of identical trees.

Every measurement here runs on an untimed attempt, outside every measured span,
and nothing in it reaches into `src`: the split is driven through its public
entry with a stand-in for the product it would have used.

This module is one of the protocol files copied into the OTHER arm's checkout,
so every name it imports from `lexic` has to be one both revisions have. The
compiled grammar's build object is the name that moves, and the stand-in never
writes it down: it is generic in whatever the parse entry it wraps accepts.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from typing import NamedTuple

from lexic.compile import CompiledGrammar
from lexic.exceptions import LexicError
from lexic.ir import IrAddress, IrAst
from lexic.model import GrammarModel
from lexic.parsing.parallel import split_model, worker_count
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.products import parse_model

type ModelProduct[M, B, C] = Callable[[IrAst, str, B, C], M]
"""A revision's model parse entry, as this benchmark uses one.

``B`` is the compiled grammar's build object and ``C`` what the revision hands a
parse beside it, and the point of the parameters is that nothing here writes
either down: the probe is handed the entry, reads them off it, and passes back
exactly what it was given.
"""


class Occupancy(NamedTuple):
    """What one untimed split attempt did, as against what it was asked for.

    :ivar declined: Why the split did not engage, or ``None`` when it did.
    :ivar plan: Digest of the DERIVED work — the pieces the split carved and
        the workers that carving admits. Identical on every attempt against
        one grammar, document and core request, so it is the field two arms
        are held to.
    :ivar workers: How many worker threads actually ran a piece of it. One
        when the split declined, so the row reports the parse that ran.
        Scheduling, not identity: reported as evidence, never compared.
    """

    declined: str | None
    plan: str
    workers: int


class _Attempt:
    """One untimed attempt's record: the pieces carved, the threads that ran.

    The two are kept apart deliberately. Piece lengths come out of the split
    plan, so they are the same on every attempt; thread idents come out of the
    executor, so they are not.
    """

    def __init__(self) -> None:
        """Start with nothing seen."""
        self.pieces: list[int] = []
        self.threads: set[int] = set()
        self.lock = threading.Lock()

    def mark(self, piece: str) -> None:
        """Record one piece and the thread that took it."""
        with self.lock:
            self.pieces.append(len(piece))
            self.threads.add(threading.get_ident())

    def workers_besides(self, driver: int) -> int:
        """How many threads other than ``driver`` ran a piece of the split.

        At least one: a split that engaged did its work somewhere, and a row
        reporting zero workers for a parse that happened would be a third
        wrong answer beside the request and the ceiling.
        """
        return len(self.threads - {driver}) or 1

    def plan(self, size: int, cores: int) -> str:
        """Digest of the pieces carved and the workers that carving admits.

        Sorted, because the ORDER pieces are handed out in is the executor's
        and varies where the carving does not. The admission ceiling rides
        along because two carvings can agree on every piece and still differ
        in how much of the document may run at once.
        """
        pieces = sorted(self.pieces)
        ceiling = worker_count(size, max(0, len(pieces) - 1), cores)
        shape = f"{ceiling}:{','.join(str(length) for length in pieces)}"
        return hashlib.sha256(shape.encode("utf-8")).hexdigest()[:16]


class _WatchedParse[M, B, C](NamedTuple):
    """The model product, marking the thread every piece was driven from.

    Wraps the product the split is handed rather than the pool, because every
    piece of concurrent work in every route — cut chunks, region pieces,
    routed interiors — reaches the engine through this one callable. The
    driver's own thread is excluded by the reader, which knows its own ident.

    The entry is supplied rather than reached for, which is what lets ``B`` and
    ``C`` — what this revision hands a parse — be read off the argument instead
    of spelled.

    :ivar parse: This revision's model parse entry.
    :ivar attempt: The record every call marks.
    """

    parse: ModelProduct[M, B, C]
    attempt: _Attempt

    def __call__(
        self,
        grammar: IrAst,
        text: str,
        build: B,
        config: C,
    ) -> M:
        """Record the piece and the calling thread, then parse as the product does."""
        self.attempt.mark(text)
        return self.parse(grammar, text, build, config)


def declined_reason(compiled: CompiledGrammar, document: str, cores: int) -> Occupancy:
    """What this artifact's split does on this document, observed not assumed.

    Asked of the split entry directly, not inferred from timings: a split that
    declines falls back to the sequential parse, so the mt cell alone cannot
    distinguish "threading bought nothing" from "nothing threaded". The plan is
    observed the same way, because the REQUEST is not an answer: the policy
    clamps useful workers by document size and cut count, and cut selection can
    clamp them again, so a 17 KiB document asked for sixteen cannot occupy more
    than eight.

    This attempt is untimed and runs outside every measured span.
    """
    attempt = _Attempt()
    split = split_model(
        _WatchedParse(parse_model, attempt),
        compiled.codegen_grammar,
        Request(document, compiled.product),
        cores,
        analysis=compiled.split_analysis or compiled.grammar,
    )
    plan = attempt.plan(len(document), cores)
    if split is None:
        return Occupancy("the unified split seam found no eligible work", plan, 1)
    return Occupancy(None, plan, attempt.workers_besides(threading.get_ident()))


def departure(split: GrammarModel, sequential: GrammarModel) -> int | None:
    """Where two models of one document first part company, as a text offset.

    ``None`` when they are equal. Read off both emissions, root first: the
    first extent whose address, span or occurrence differs names where the
    split's carving left the sequential one — the start of the item the two
    read differently, not the root that merely contains it. Two models that
    spell different texts part at their first differing character; two that
    differ only where nothing is emitted are reported at the start.

    Untimed and cold: it runs only on a row whose split is under suspicion.
    """
    if split == sequential:
        return None
    one, other = split.emit_addressed(), sequential.emit_addressed()
    if one.text != other.text:
        pairs = zip(one.text, other.text, strict=False)
        return next(
            (at for at, (a, b) in enumerate(pairs) if a != b),
            min(len(one.text), len(other.text)),
        )
    for mine, theirs in zip(one.extents, other.extents, strict=False):
        if mine != theirs or _occupant(split, mine.address) != _occupant(
            sequential, theirs.address
        ):
            return min(mine.span.start, theirs.span.start)
    if len(one.extents) != len(other.extents):
        shorter = min(len(one.extents), len(other.extents))
        return max(one.extents, other.extents, key=len)[shorter].span.start
    return 0


def _occupant(model: GrammarModel, address: IrAddress) -> tuple[type, str]:
    """What stands at ``address``: its class, and its spelling if it is a leaf.

    A container is compared by class alone — its contents are later extents of
    their own, and comparing it whole would make the root the first difference.
    """
    part = model.occurrence(address)
    return type(part), "" if isinstance(part, tuple) else str(part)


def split_departure(compiled: CompiledGrammar, document: str, cores: int) -> int | None:
    """Where this artifact's split at ``cores`` departs from its sequential model.

    ``None`` when the split declines or builds the sequential model, and when
    the sequential parse refuses the document: a refusal proves nothing about
    the split, so it must never read as one that departed.

    That parse runs FIRST: on a grammar whose sequential route is a
    whole-document chart, it is the process's peak, and a split run before it
    leaves its own high-water mark underneath. On a 34 KB witness,
    sequential then two workers peaked at 12.0 GB; three split attempts then
    sequential, at 15.4 GB.

    Asked of one worker count per process, by the caller, for the same reason.
    """
    ask = Request(document, compiled.product)
    try:
        sequential = parse_model(
            compiled.codegen_grammar, document, compiled.product, ask.config
        )
    except LexicError:
        return None
    split = split_model(
        parse_model,
        compiled.codegen_grammar,
        ask,
        cores,
        analysis=compiled.split_analysis or compiled.grammar,
    )
    return None if split is None else departure(split, sequential)
