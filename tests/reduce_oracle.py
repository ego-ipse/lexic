"""Temporary fused-reduce oracle while the legacy engine twin is deleted.

Production has one product: model parsing. Tests that still differential-check
the reducer-derived artefact keep the old PDA-first/fused completion here until
TODO 1g removes that machinery and its route-specific assertions together.
"""

from __future__ import annotations

from dataclasses import dataclass

from lexic.ir import IrAst, IrSelf
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_reduce_pda
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail
from lexic.parsing.pda.runtime.kernel.reduce_runtime import pda_reduce
from lexic.parsing.products import earley_reduce


@dataclass(frozen=True)
class ReduceOracle:
    """The compiled legacy route retained only for differential assertions."""

    grammar: IrAst
    reducer: Reducer
    pda: PdaTables
    earley_grammar: IrAst


_CACHE: dict[tuple[int, int], ReduceOracle] = {}


def reduce_oracle(grammar: IrAst, reducer: Reducer) -> ReduceOracle:
    """Compile and identity-memoise the retired reduce route for tests only."""
    key = (id(grammar), id(reducer))
    cached = _CACHE.get(key)
    if cached is not None and cached.grammar is grammar and cached.reducer is reducer:
        return cached
    lifted = lift_optional_nullables(grammar)
    instance = normalize(lifted)
    product = ReduceOracle(
        grammar,
        reducer,
        compile_reduce_pda(lifted, instance, reducer),
        instance,
    )
    _CACHE[key] = product
    return product


def reduce_one(grammar: IrAst, text: str, reducer: Reducer) -> IrSelf:
    """Run one whole-document reduction through the retired fused route."""
    product = reduce_oracle(grammar, reducer)
    try:
        return pda_reduce(product.pda, text)
    except PdaFail:
        return earley_reduce(product.earley_grammar, text, reducer)


def reset_reduce_oracle() -> None:
    """Clear the test-only identity memo."""
    _CACHE.clear()
