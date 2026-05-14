"""Shared helpers for codegen unit tests."""

from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrSequence,
    Quantifier,
)


def make_charclass_literal_group() -> IrGroup:
    """Return the IrGroup for ([a-h] 'x') used in alias and emitter tests."""
    return IrGroup(
        IrAlternation(
            (
                IrSequence(
                    (
                        IrItem(IrCharClass("a-h"), Quantifier(1, 1)),
                        IrItem(IrLiteral("x"), Quantifier(1, 1)),
                    )
                ),
            )
        )
    )
