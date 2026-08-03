"""The session cursor — a root, its ladder, its readings.

A session is a LADDER of rungs: Flavour first, Text last, any number of
Grammar rungs between; a grammar is a root's text; edits cascade
DOWNWARD only. Every reading is one public lexic call, recorded as its
product or its real refusal — praxis never computes.

Engine-style cursor tier: plain ``None``, ``__slots__``, mutation in
place. Strictness is the scene's contract (:mod:`opsis.opsis.scene`),
not the cursor's.
"""

from __future__ import annotations

from typing import Callable

from lexic.compile import (
    CompiledGrammar,
    Directives,
    Vocabulary,
    compile_ast,
    compile_text,
    load_ir,
    parse_grammar,
)
from lexic.compile.notation.loader import load_flavour
from lexic.exceptions import LexicError
from lexic.grammars import get_flavour
from lexic.ir import IrAst, IrFlavour, IrSelf

__all__ = ["Ladder", "Root", "Rung", "root_flavour", "root_manifest", "root_notation"]

GrammarReader = Callable[[str, Vocabulary, Directives], CompiledGrammar]
InstanceReader = Callable[[str], IrSelf]


class Root:
    """The bottom of the ladder — who reads grammar texts.

    ``read_grammar`` is the COMPILER reading every grammar rung gets
    (the defining relation); ``read_instance`` is rung 1's INSTANCE
    reading — the root's own surface reading its first text — or
    ``None`` where the root has no instance surface. ``comment_forms``
    is whether the root's SOURCE surface can spell a ``@directive`` —
    a comment-less surface draws its directive chips disabled, with
    that reason.
    """

    __slots__ = ("read_grammar", "read_instance", "comment_forms")

    def __init__(
        self,
        read_grammar: GrammarReader,
        read_instance: InstanceReader | None,
        comment_forms: bool,
    ) -> None:
        self.read_grammar = read_grammar
        self.read_instance = read_instance
        self.comment_forms = comment_forms


def _has_comments(flavour: IrFlavour) -> bool:
    """Whether the flavour's surface can spell a directive comment."""
    return bool(flavour.line_comment or flavour.block_comment)


def root_flavour(name: str) -> Root:
    """The common root — a registered flavour reads grammar texts."""
    flavour = get_flavour(name)  # an unknown name refuses here, at construction
    return Root(
        lambda text, vocabulary, directives: compile_text(
            text, flavour=name, vocabulary=vocabulary, directives=directives
        ),
        lambda text: parse_grammar(text, flavour),
        _has_comments(flavour),
    )


def root_manifest(manifest_text: str) -> Root:
    """A session flavour — the manifest is itself a text the notation reads.

    The loaded instance stays SESSION-LOCAL: it rides ``flavour=`` as a
    live instance, so the process-wide registry is untouched and a
    shipped singleton under the same name is never shadowed.
    """
    flavour = load_flavour(manifest_text)
    return Root(
        lambda text, vocabulary, directives: compile_text(
            text, flavour=flavour, vocabulary=vocabulary, directives=directives
        ),
        lambda text: parse_grammar(text, flavour),
        _has_comments(flavour),
    )


def root_notation() -> Root:
    """The IR-constructor root — grammar rungs are notation texts.

    Reads through ``compile_ast`` directly: no emit round-trip, so the
    AST's own ``semantic`` flags survive and nothing is bound to one
    flavour's spelling. The notation carries no comments — flags ride
    the AST itself — so directive chips draw disabled on this root.
    """
    return Root(
        lambda text, vocabulary, directives: compile_ast(
            _notation_ast(text), vocabulary=vocabulary, directives=directives
        ),
        _notation_ast,
        False,
    )


def _notation_ast(text: str) -> IrAst:
    """One notation read, narrowed to a grammar."""
    return IrAst.ensure(load_ir(text), "notation root: a grammar expression")


class Rung:
    """One level: a text, its reading input, and its readings.

    ``directives`` and ``vocabulary`` are the rung's parameter state —
    the chips and plugs of the reading input; they ride every re-read.
    """

    __slots__ = ("text", "directives", "vocabulary", "instance", "compiled", "errors")

    def __init__(self) -> None:
        self.text: str = ""
        self.directives: Directives = Directives()
        self.vocabulary: Vocabulary = Vocabulary()
        self.instance: IrSelf | None = None
        self.compiled: CompiledGrammar | None = None
        self.errors: dict[str, str] = {}


class Ladder:
    """The session cursor: a root plus rungs; edits cascade DOWNWARD only.

    Every rung's text has up to two readings. The COMPILER reading is
    the root's — every grammar rung is the root's text. The INSTANCE
    reading is the rung above's: rung 1 is read by the root's own
    surface, deeper rungs by the compiled grammar above. The terminal
    rung is instance-only: Text is last, BY POSITION.
    """

    __slots__ = ("root", "rungs")

    def __init__(self, root: Root) -> None:
        self.root = root
        self.rungs: list[Rung] = []

    def edit(
        self,
        i: int,
        text: str,
        *,
        directives: Directives | None = None,
        vocabulary: Vocabulary | None = None,
    ) -> None:
        """Set rung ``i``'s reading input; re-read it and every rung below.

        Growth flips the previously-terminal rung from Text to Grammar
        (Text is last by position), so an append re-reads that rung too
        — still downward-only relative to every rung whose kind stands.
        """
        grew = len(self.rungs) <= i
        while len(self.rungs) <= i:
            self.rungs.append(Rung())
        rung = self.rungs[i]
        rung.text = text
        if directives is not None:
            rung.directives = directives
        if vocabulary is not None:
            rung.vocabulary = vocabulary
        start = min(i, len(self.rungs) - 2) if grew and len(self.rungs) > 1 else i
        for j in range(start, len(self.rungs)):
            self._read(j)

    def _read(self, i: int) -> None:
        """One rung's readings, recorded as products or real refusals."""
        rung, above = self.rungs[i], (self.rungs[i - 1] if i else None)
        rung.instance = rung.compiled = None
        rung.errors = {}
        terminal = i == len(self.rungs) - 1
        if not terminal:
            try:
                rung.compiled = self.root.read_grammar(
                    rung.text, rung.vocabulary, rung.directives
                )
            except (LexicError, RecursionError) as exc:
                rung.errors["compiled"] = f"{type(exc).__name__}: {exc}"
        if above is not None and above.compiled is not None:
            try:
                rung.instance = above.compiled.parse(rung.text)
            except (LexicError, RecursionError) as exc:
                rung.errors["instance"] = f"{type(exc).__name__}: {exc}"
        elif above is None and self.root.read_instance is not None and not terminal:
            try:
                rung.instance = self.root.read_instance(rung.text)
            except (LexicError, RecursionError) as exc:
                rung.errors["instance"] = f"{type(exc).__name__}: {exc}"
