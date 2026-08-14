"""The pipeline's moments, and how each one is spelled.

The same language as written, in its canonical normal form, as codegen cut
it for the parser, and as the Earley engine lifts it. None is more true than
the others; a view drawing one while another view draws a second is why a
choice the machine made had no node to light.
"""

from __future__ import annotations

from praxis.reading import Reading

from lexic.compile import CompiledGrammar, canonical_grammar
from lexic.exceptions import LexicError
from lexic.grammars import get_flavour
from lexic.ir import IrAst
from lexic.parsing.fold import lift_optional_nullables

__all__ = ["FORMS", "form_of", "spelled"]


FORMS = ("source", "canonical", "codegen", "lifted")


def form_of(machine: CompiledGrammar, reading: Reading, which: str) -> IrAst:
    """This reader at one moment of the pipeline."""
    if which == "lifted":
        # what the Earley engine actually runs: the codegen grammar with its
        # optional nullables lifted. The last moment before the parse, and
        # the one no view was drawing.
        return lift_optional_nullables(machine.codegen_grammar)
    if which == "codegen":
        return machine.codegen_grammar
    if which == "canonical":
        return canonical_grammar(
            reading.reader_text, get_flavour(reading.flavour or "gbnf")
        )
    return machine.grammar


def spelled(reading: Reading, shown: IrAst | None, form: str) -> str:
    """This form as grammar TEXT — what the reader displays.

    The source form is the file as written; the other two are spelled by the
    flavour that read it, so a form is never shown as a description of
    itself. If it cannot be spelled, the reader keeps showing what it has.
    """
    if form == "source" or shown is None:
        return reading.reader_text
    try:
        return get_flavour(reading.flavour or "gbnf").apply(shown)
    except LexicError, RecursionError, ValueError:
        return reading.reader_text
