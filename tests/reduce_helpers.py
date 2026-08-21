"""Shared assertions for the one compiled-artefact reduction path."""

from __future__ import annotations

from lexic.compile import compile_ast
from lexic.ir import IrAst, IrSelf
from lexic.parsing import Reducer


def reduce_text(grammar: IrAst, text: str, reducer: Reducer) -> IrSelf:
    """Reduce ``text`` through the sole production route, sequentially."""
    return compile_ast(grammar).reduce(text, reducer, cores=1)
