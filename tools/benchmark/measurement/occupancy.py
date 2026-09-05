"""What a split attempt DID, as against what it was asked for.

The request is not an observation. Production clamps useful workers by document
size and cut count, cut selection can clamp them again, and the executor only
starts the threads its submitted tasks demand — so a row that reports the
number it asked for certifies nothing, and two arms echoing the same request
can divide one document differently and still compare.

Every measurement here runs on an untimed attempt, outside every measured span,
and nothing in it reaches into `src`: the split is driven through its public
entry with a stand-in for the product it would have used.
"""

from __future__ import annotations

import threading
from typing import NamedTuple

from lexic.compile import CompiledGrammar
from lexic.ir import IrAst
from lexic.parsing import ModelExecutable
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.products import parse_model


class Occupancy(NamedTuple):
    """What one untimed split attempt did, as against what it was asked for.

    :ivar declined: Why the split did not engage, or ``None`` when it did.
    :ivar workers: How many worker threads actually ran a piece of it. One
        when the split declined, so the row reports the parse that ran.
    """

    declined: str | None
    workers: int


class _CountingParse:
    """The model product, recording which threads it was driven from.

    Wraps the product the split is handed rather than the pool, because every
    piece of concurrent work in every route — cut chunks, region pieces,
    routed interiors — reaches the engine through this one callable. The
    driver's own thread is excluded by the caller, which knows its own ident.
    """

    def __init__(self) -> None:
        """Start with no threads seen."""
        self.threads: set[int] = set()
        self.lock = threading.Lock()

    def __call__[M](
        self,
        grammar: IrAst,
        text: str,
        binding: ModelExecutable[M],
        resolve: Resolver | None = None,
    ) -> M:
        """Record the calling thread, then parse as the product does."""
        with self.lock:
            self.threads.add(threading.get_ident())
        return parse_model(grammar, text, binding, resolve)

    def workers_besides(self, driver: int) -> int:
        """How many threads other than ``driver`` ran a piece of the split.

        At least one: a split that engaged did its work somewhere, and a row
        reporting zero workers for a parse that happened would be a third
        wrong answer beside the request and the ceiling.
        """
        return len(self.threads - {driver}) or 1


def declined_reason(compiled: CompiledGrammar, document: str, cores: int) -> Occupancy:
    """What this artifact's split does on this document, observed not assumed.

    Asked of the split entry directly, not inferred from timings: a split that
    declines falls back to the sequential parse, so the mt cell alone cannot
    distinguish "threading bought nothing" from "nothing threaded". The worker
    count is observed the same way, because the REQUEST is not an answer: the
    policy clamps useful workers by document size and cut count, and cut
    selection can clamp them again, so a 17 KiB document asked for sixteen
    cannot occupy more than eight.

    This attempt is untimed and runs outside every measured span.
    """
    counted = _CountingParse()
    request = Request(document, compiled.product, None)
    split = split_model(
        counted,
        compiled.codegen_grammar,
        request,
        cores,
        analysis=compiled.split_analysis or compiled.grammar,
    )
    if split is None:
        return Occupancy("the unified split seam found no eligible work", 1)
    return Occupancy(None, counted.workers_besides(threading.get_ident()))
