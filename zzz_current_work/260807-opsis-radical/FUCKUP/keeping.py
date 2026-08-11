"""The KEEPING relation — a thing, as the artefacts it can be written as.

The family is decided by the reduction's CODOMAIN, never by a target flag:
a reader keeps as its twin module and as the IR notation; a parsed value
keeps as an importable value module. Every artefact is LOADED BACK before it
counts — an artefact nobody can read is a file, not a projection.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence

from lexic.compile import CompiledGrammar
from lexic.compile.module.export import export_source
from lexic.compile.notation import emit_ir, load_ir
from lexic.exceptions import LexicError
from reading import turn
from relate import KINDS, SUBJECT, Relation, Role, Thing

__all__ = ["Artefact", "Keeping"]


class Artefact:
    """One written form, and the witness that it can be read back."""

    __slots__ = ("chars", "name", "text", "witness", "words")

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text
        self.chars = len(text)
        self.witness = "unwitnessed"
        self.words = ""


class Keeping(Relation):
    """What this thing can be written as, and whether it survives the trip."""

    kind = "keeping"
    slots = (SUBJECT,)

    def __init__(self, rid: str, cast: Mapping[str, Thing]) -> None:
        super().__init__(rid, cast)
        self.artefacts: list[Artefact] = []

    @classmethod
    def licenses(cls, role: Role, thing: Thing) -> bool:
        """Only something the engine compiles has a twin to keep."""
        return role is SUBJECT and turn(thing) is not None

    def label(self) -> str:
        return f"{self.cast[SUBJECT.name].name} — as artefacts"

    def hold(self) -> None:
        if self.held:
            return
        self.held = True
        turned = turn(self.cast[SUBJECT.name])
        if turned is None:
            return
        self.artefacts = [self._twin(turned.machine), self._notation(turned.machine)]

    def _twin(self, compiled: CompiledGrammar) -> Artefact:
        """The importable twin module — witnessed by Python itself parsing it."""
        try:
            source = export_source(compiled)
        except (LexicError, RecursionError, ValueError) as refusal:
            return _refused("the twin module", refusal)
        made = Artefact("the twin module", source)
        try:
            ast.parse(source)
        except SyntaxError as broken:
            made.witness = "FAILS"
            made.words = f"python cannot parse what we wrote — {broken.msg}"
            return made
        made.witness = "holds"
        made.words = "python parses it; the module names the grammar's own rules"
        return made

    def _notation(self, compiled: CompiledGrammar) -> Artefact:
        """The IR notation — witnessed by reading it back into live IR."""
        grammar = compiled.grammar
        try:
            text = emit_ir(grammar)
        except (LexicError, RecursionError, ValueError, TypeError) as refusal:
            return _refused("the IR notation", refusal)
        made = Artefact("the IR notation", text)
        try:
            back = load_ir(text)
        except (LexicError, RecursionError, ValueError) as refusal:
            made.witness = "FAILS"
            made.words = f"it does not read back — {refusal}"
            return made
        same = back == grammar
        made.witness = "holds" if same else "FAILS"
        made.words = (
            "read back into live IR, equal to the grammar it came from"
            if same
            else "it reads back, but as a different value"
        )
        return made

    def facts(self) -> str:
        held = sum(1 for made in self.artefacts if made.witness == "holds")
        return f"{len(self.artefacts)} artefacts · {held} witnessed"

    def parts(self) -> Sequence[Thing]:
        return list(self.cast.values())


def _refused(name: str, refusal: Exception) -> Artefact:
    """A form this thing cannot take is a RESULT, and says why."""
    made = Artefact(name, "")
    made.witness = "refused"
    made.words = str(refusal)[:160]
    return made


KINDS[Keeping.kind] = Keeping
