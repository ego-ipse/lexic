"""Shared fixtures for the product ABI's own test files.

A minimal declared record class, used only by identity (``cls=Pair`` /
``is Pair``, never actually constructed), and a minimal ``OperandTables``
builder sharing one root finalizer and one meaning comparator — duplicated
verbatim enough times across ``parsing/product/``'s test files to warrant one
shared home, matching ``parsing_helpers.py``'s precedent for this directory.
"""

from __future__ import annotations

from lexic.parsing.product import (
    CaptureMode,
    CaptureSpec,
    LoweredRoute,
    OperandTables,
    RecordConstructor,
    RecordOp,
    RuleProduct,
)

ROOTS = (lambda carry, _verdicts: carry,)
MEANINGS = (lambda left, right: left == right,)


class Pair(tuple):
    """A minimal declared record class with two fields, identity only."""

    @classmethod
    def fast_construct(cls):
        """Return this record's positional construction licence."""
        return (cls, {}, ("a", "b"))


def operands(
    constructors: tuple[RecordConstructor, ...] = (),
    routes: tuple[LoweredRoute, ...] = (),
) -> OperandTables:
    """A minimal OperandTables sharing the module's root/meaning callables."""
    return OperandTables(
        constants=(),
        constructors=constructors,
        sequences=(),
        mappings=(),
        meanings=MEANINGS,
        roots=ROOTS,
        routes=routes,
        continuations=(),
    )


def two_text_capture_rule() -> RuleProduct:
    """A RECORD rule with two required TEXT captures — the corpus-wide shape
    a declared two-field record builds from."""
    return RuleProduct(
        captures=(
            CaptureSpec(int(CaptureMode.TEXT), 0),
            CaptureSpec(int(CaptureMode.TEXT), 1),
        ),
        completion=RecordOp(0),
        n_items=2,
    )
