"""Shared helpers for codegen unit tests."""

from __future__ import annotations

from lexic.ir.base import IrChr
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrSequence,
)

__all__ = ["make_charclass_literal_group"]


def make_charclass_literal_group() -> IrAlternation:
    """Return the IrAlternation for ([a-h] 'x') used in alias tests."""
    return IrAlternation(
        IrSequence(
            IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("h"))), IrQuantifier(1, 1)),
            IrItem(IrLiteral("x"), IrQuantifier(1, 1)),
        )
    )
