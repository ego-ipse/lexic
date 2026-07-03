"""Shared helpers for codegen unit tests."""

from __future__ import annotations

import ast
import importlib.util
import os
import tempfile
import types

from lexic.ir.base import IrChr, IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrSequence,
)
from lexic.ir.spec import RuleSpec
from tests.unit.lexic.conftest import make_inner_outer_specs, make_spec

__all__ = [
    "load_emitted",
    "make_charclass_literal_group",
    "make_inner_outer_specs",
    "make_two_digit_specs",
]


def load_emitted(src: str) -> types.ModuleType:
    """Load emitted Python source into a fresh module for runtime inspection.

    Validates syntax via ast.parse first, then loads via importlib — avoids the
    exec() builtin in callers while still testing actual runtime class behaviour.
    Writes to a tempfile and always cleans it up.
    """
    ast.parse(src)  # raises SyntaxError early if source is invalid
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        spec = importlib.util.spec_from_file_location("_emitted_test", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"importlib could not locate {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.unlink(path)


def make_two_digit_specs() -> tuple[RuleSpec, RuleSpec]:
    """Return two specs matching ``[0-9]+``, named ``a`` and ``b``.

    Used in tests that verify alias deduplication: two rules with identical
    charclass patterns must share a single module-level alias.

    :returns: ``(s1, s2)`` tuple of :class:`~lexic.ir.spec.RuleSpec`.
    """
    s1 = make_spec(
        "a",
        "value_str",
        [IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9"))), IrQuantifier(1, IrNone))],
    )
    s2 = make_spec(
        "b",
        "value_str",
        [IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9"))), IrQuantifier(1, IrNone))],
    )
    return s1, s2


def make_charclass_literal_group() -> IrAlternation:
    """Return the IrAlternation for ([a-h] 'x') used in alias and emitter tests."""
    return IrAlternation(
        IrSequence(
            IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("h"))), IrQuantifier(1, 1)),
            IrItem(IrLiteral("x"), IrQuantifier(1, 1)),
        )
    )
