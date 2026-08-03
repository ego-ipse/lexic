"""An emission as the document it is, before it is a string.

A flavour does not build text by concatenation: it applies emit actions
that produce a layout document — a tree of width-aware combinators —
and rendering that document at a width is the last step. Getting at the
document rather than the string is what makes the width a control.
"""

from __future__ import annotations

from lexic.grammars import get_flavour
from lexic.ir import IrAst, IrDoc

__all__ = ["emit_doc"]


def emit_doc(ast: IrAst, surface: str) -> IrDoc:
    """The layout document a flavour's emit half builds for this grammar.

    :param ast: The grammar to emit.
    :param surface: Which flavour spells it.
    :returns: The document, unrendered — rendering it is the caller's
        choice of width.
    """
    flavour = get_flavour(surface)
    return IrDoc.ensure(
        flavour.actions.eval(flavour, ast, ()), f"{surface}: an emission"
    )
