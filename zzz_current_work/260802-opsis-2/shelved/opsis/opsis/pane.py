"""What a window IS, and the one question every builder asks.

A leaf both halves of the fan sit on: the record saying what a window
is called and how big, the two ways of getting at the grammar a reading
IS, and the per-reading state a window keeps between openings. Neither
half has to import the other to ask.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from lexic.compile import CompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrDoc
from opsis.kairos.constrain import Cursors
from opsis.kairos.resume import Resumes
from opsis.praxis.reading import Reading, self_compiled
from opsis.praxis.session import Session

__all__ = [
    "CURSORS",
    "RESUMES",
    "SPELLABLE",
    "WIDTHS",
    "Pane",
    "artefact",
    "grammar_of",
    "read_by",
]

RESUMES = Resumes()
"""Every reading's growing chart — dropped when its grammar re-reads."""

CURSORS = Cursors()
"""Every reading's constraint cursor — thrown away when it re-reads."""

WIDTHS: dict[str, int] = {}
"""The width each reading's document window is rendered at."""

SPELLABLE = ("gbnf", "abnf", "ebnf")
"""Surfaces the exporter can spell a module's docstrings in."""


class Pane(NamedTuple):
    """One window: what it is called, how big, and how to build it."""

    title: str
    size: tuple[int, int]
    build: Callable[[], list[IrDoc]]


def artefact(reading: Reading) -> CompiledGrammar | None:
    """The grammar this reading IS, however it came to be one.

    A grammar reading compiled one; a flavour reading carries one — its
    own self-grammar, which is a grammar like any other and gets the
    same windows. That equivalence is the meta ladder, and it is one
    function rather than a special case in each of them.
    """
    if reading.compiled is not None:
        return reading.compiled
    return self_compiled(reading.flavour) if reading.flavour is not None else None


def grammar_of(reading: Reading) -> CompiledGrammar:
    """The grammar this reading is, or the refusal saying it is not one."""
    held = artefact(reading)
    if held is None:
        raise UnsupportedConstructError(f"{reading.title} is not a grammar")
    return held


def read_by(session: Session, reading: Reading) -> CompiledGrammar:
    """The compiled grammar that read this text, or the refusal."""
    above = session.readings.get(reading.reader)
    under = artefact(above) if above is not None and reading.text else None
    if under is None:
        raise UnsupportedConstructError(
            f"{reading.title} was not read by a compiled grammar"
        )
    return under
