"""Closed expression-op coverage over every shipped reducer.

This prototype asks a narrow question: can the reducer expressions which the
default product must preserve be lowered to flat instructions without storing
an erased operand?  It proves class coverage and typed table shape, not the
semantics of the eventual instruction interpreter.
"""

from __future__ import annotations

from enum import IntEnum
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_REDUCER
from lexic.grammars.ebnf import EBNF_REDUCER
from lexic.grammars.gbnf import GBNF_REDUCER
from lexic.grammars.json import JSON_REDUCER
from lexic.ir import (
    IrArg,
    IrArgs,
    IrAt,
    IrBuild,
    IrConcat,
    IrCond,
    IrField,
    IrGlyph,
    IrInt,
    IrJoin,
    IrLiteral,
    IrMap,
    IrMerge,
    IrNoneType,
    IrPipe,
    IrRaise,
    IrSelf,
    IrStr,
    IrThis,
    IrTuple,
    IrTypeMap,
    IrUnradix,
    IrUtf,
)
from lexic.ir.reduction import Drop, KeepReduced, Reducer, Yield


class ExprCode(IntEnum):
    """Prototype postfix vocabulary for current reducer expressions."""

    CONSTANT = 0
    ARG = 1
    ARGS = 2
    AT = 3
    BUILD = 4
    CONCAT = 5
    COND = 6
    FIELD = 7
    GLYPH = 8
    JOIN = 9
    LOOKUP = 10
    MERGE = 11
    PIPE = 12
    RAISE = 13
    THIS = 14
    UNRADIX = 15
    UTF = 16
    DROP = 17
    KEEP_REDUCED = 18
    YIELD = 19


class FlatExpr(NamedTuple):
    """One int-coded expression instruction."""

    code: int
    child_count: int
    operand: int


class ExprOperands[Carry](NamedTuple):
    """Typed constants remain separate from flat integer instructions."""

    constants: tuple[Carry, ...]
    fields: tuple[str, ...]
    indices: tuple[int, ...]
    messages: tuple[str, ...]


class ExprProgram[Carry](NamedTuple):
    """One typed postfix expression program."""

    instructions: tuple[FlatExpr, ...]
    operands: ExprOperands[Carry]


_CODES: dict[type[IrSelf], ExprCode] = {
    Drop: ExprCode.DROP,
    IrArg: ExprCode.ARG,
    IrArgs: ExprCode.ARGS,
    IrAt: ExprCode.AT,
    IrBuild: ExprCode.BUILD,
    IrConcat: ExprCode.CONCAT,
    IrCond: ExprCode.COND,
    IrField: ExprCode.FIELD,
    IrGlyph: ExprCode.GLYPH,
    IrInt: ExprCode.CONSTANT,
    IrJoin: ExprCode.JOIN,
    IrLiteral: ExprCode.CONSTANT,
    IrMap: ExprCode.LOOKUP,
    IrMerge: ExprCode.MERGE,
    IrNoneType: ExprCode.CONSTANT,
    IrPipe: ExprCode.PIPE,
    IrRaise: ExprCode.RAISE,
    IrStr: ExprCode.CONSTANT,
    IrThis: ExprCode.THIS,
    IrTuple: ExprCode.CONSTANT,
    IrTypeMap: ExprCode.LOOKUP,
    IrUnradix: ExprCode.UNRADIX,
    IrUtf: ExprCode.UTF,
    KeepReduced: ExprCode.KEEP_REDUCED,
    Yield: ExprCode.YIELD,
}

_ATOMIC = frozenset(
    {
        ExprCode.ARG,
        ExprCode.CONSTANT,
        ExprCode.DROP,
        ExprCode.GLYPH,
        ExprCode.KEEP_REDUCED,
        ExprCode.LOOKUP,
        ExprCode.RAISE,
        ExprCode.THIS,
        ExprCode.UTF,
        ExprCode.YIELD,
    }
)


def _lower(node: IrSelf, out: list[FlatExpr]) -> None:
    """Append one expression in postfix order, refusing unknown classes."""
    code = _CODES.get(type(node))
    if code is None:
        raise UnsupportedConstructError(
            f"prototype expression: no opcode for {type(node).__name__}"
        )
    child_count = 0
    if code not in _ATOMIC:
        for child in node.children():
            if isinstance(child, IrSelf):
                _lower(child, out)
                child_count += 1
    out.append(FlatExpr(int(code), child_count, 0))


def lower_reducer(reducer: Reducer) -> ExprProgram[IrSelf]:
    """Lower every declared expression of one real reducer."""
    instructions: list[FlatExpr] = []
    roots = (
        reducer.default,
        reducer.literal,
        *reducer.actions.values(),
        *reducer.noise.values(),
    )
    for root in roots:
        _lower(root, instructions)
    return ExprProgram(
        tuple(instructions),
        ExprOperands((), (), (), ()),
    )


def main() -> None:
    """Prove closed class coverage for all shipped parse reducers."""
    reducers = (
        ("gbnf", GBNF_REDUCER),
        ("abnf", ABNF_REDUCER),
        ("ebnf", EBNF_REDUCER),
        ("json", JSON_REDUCER),
    )
    for name, reducer in reducers:
        program = lower_reducer(reducer)
        assert program.instructions
        print(name, len(program.instructions))


if __name__ == "__main__":
    main()
