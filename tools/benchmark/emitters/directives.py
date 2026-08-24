"""Directive data shared by the benchmark grammar emitters."""

from __future__ import annotations

from lexic.ir import IrAst, inline_refs

Marks = tuple[frozenset[str], frozenset[str]]
"""The ``(lexical, non_semantic)`` directive sets an emitter translates."""

NO_MARKS: Marks = (frozenset(), frozenset())
"""No directives: the grammar exactly as authored."""


def inlined_marks(ast: IrAst, marks: Marks) -> IrAst:
    """Translate directives for tools with no tree-filtering rule syntax."""
    folded = marks[0] | marks[1]
    return inline_refs(ast, folded) if folded else ast
