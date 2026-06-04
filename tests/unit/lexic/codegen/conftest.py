"""Shared helpers for codegen unit tests."""

from __future__ import annotations

import ast
import importlib.util
import os
import tempfile
import types

from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrSequence,
)


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


def make_charclass_literal_group() -> IrGroup:
    """Return the IrGroup for ([a-h] 'x') used in alias and emitter tests."""
    return IrGroup(
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass("a-h"), IrQuantifier(1, 1)),
                IrItem(IrLiteral("x"), IrQuantifier(1, 1)),
            )
        )
    )
