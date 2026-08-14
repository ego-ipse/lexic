"""The artefacts a reading can be written as — and the witness for each.

An artefact nobody can read back is a file, not a projection. So nothing here
counts as an artefact until it has been LOADED BACK: Lexic's self-grammar has
to cross-check the twin, and the IR notation has to read back live IR EQUAL to
the grammar it came from.

The family is decided by the codomain, never by a target flag — a reader
keeps as its twin and as its notation; what a parsed value keeps is a
different question, asked where the value is.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar, verify_module
from lexic.compile.module.export import export_source
from lexic.compile.notation import emit_ir, load_ir
from lexic.exceptions import LexicError

__all__ = ["Artefact", "keep", "licences"]


class Artefact:
    """One written form, and whether it survives the trip back."""

    __slots__ = ("chars", "name", "witness", "words")

    def __init__(self, name: str, chars: int, witness: str, words: str) -> None:
        self.name = name
        self.chars = chars
        self.witness = witness
        self.words = words

    def line(self) -> str:
        return f"{self.name} · {self.chars:,} chars · {self.witness} — {self.words}"


_KEPT: dict[tuple[int, int], tuple[CompiledGrammar, tuple[Artefact, ...]]] = {}
FORMS = ("the twin module", "the IR notation")


def licences(_compiled: CompiledGrammar) -> tuple[str, ...]:
    """The cheap forms a compiled grammar can offer before witnessing."""
    return FORMS


def twin(compiled: CompiledGrammar) -> Artefact:
    """The twin module — parsed and cross-checked by Lexic's self-grammar."""
    try:
        source = export_source(compiled)
    except (LexicError, RecursionError, ValueError) as refusal:
        return Artefact("the twin module", 0, "refused", str(refusal)[:120])
    try:
        verify_module(compiled, source)
    except (LexicError, RecursionError, ValueError) as refusal:
        return Artefact(
            "the twin module", len(source), "FAILS", str(refusal)[:120]
        )
    return Artefact(
        "the twin module",
        len(source),
        "holds",
        "lexic reads it back and cross-checks every binding",
    )


def notation(compiled: CompiledGrammar) -> Artefact:
    """The IR notation — witnessed by reading it back into live IR."""
    grammar = compiled.grammar
    try:
        text = emit_ir(grammar)
    except (LexicError, RecursionError, TypeError, ValueError) as refusal:
        return Artefact("the IR notation", 0, "refused", str(refusal)[:120])
    try:
        back = load_ir(text)
    except (LexicError, RecursionError, ValueError) as refusal:
        return Artefact("the IR notation", len(text), "FAILS", str(refusal)[:120])
    same = back == grammar
    return Artefact(
        "the IR notation",
        len(text),
        "holds" if same else "FAILS",
        "reads back equal to the grammar it came from"
        if same
        else "reads back as a different value",
    )


def keep(compiled: CompiledGrammar, generation: int = 0) -> list[Artefact]:
    """Every form this reader can be written as, each already witnessed."""
    key = (id(compiled), generation)
    cached = _KEPT.get(key)
    if cached is None or cached[0] is not compiled:
        cached = (compiled, (twin(compiled), notation(compiled)))
        _KEPT[key] = cached
        if len(_KEPT) > 64:
            del _KEPT[next(iter(_KEPT))]
    return list(cached[1])
