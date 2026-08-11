"""A reading, and the room each of its surfaces needs.

The lesson the last build paid for: every picture that failed, failed on
PLACEMENT. The same rule graph is legible in a window and a smear in a
quarter-width column; 126 clones cannot be shown in 400px at any spacing.
Drawing was never the problem — the surface was being asked to live somewhere
it does not fit.

So appetite is part of what a surface IS. A facet declares the room it needs
in characters, not pixels: how wide its widest line is and how many lines it
has. The arrangement gives it that or opens it as a window; nothing silently
crushes a view into a column and calls the result broken.
"""

from __future__ import annotations

import time
from pathlib import Path

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import LexicError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.model import GrammarModel

__all__ = ["Facet", "Reading", "Span", "read"]

CANDIDATES = (GBNF_FLAVOUR, ABNF_FLAVOUR, EBNF_FLAVOUR)


class Span:
    """One occurrence: a value, at a place, under a name."""

    __slots__ = ("depth", "end", "field", "rule", "start")

    def __init__(self, start: int, depth: int, rule: str, field: str) -> None:
        self.start = start
        self.end = start
        self.depth = depth
        self.rule = rule
        self.field = field


class Facet:
    """A surface, and the room it needs to be itself.

    :ivar wide: the widest line it has, in characters.
    :ivar tall: how many lines it has.

    A facet that cannot be given its room is opened as a window rather than
    squeezed — that decision belongs to the arrangement, but the number
    belongs here, because only the surface knows how big it is.
    """

    __slots__ = ("kind", "name", "tall", "wide")

    def __init__(self, name: str, kind: str, wide: int, tall: int) -> None:
        self.name = name
        self.kind = kind
        self.wide = wide
        self.tall = tall

    def wire(self) -> str:
        return f"#FACET {self.name} {self.kind} needs {self.wide} {self.tall}"


def turn(text: str) -> tuple[CompiledGrammar, str] | None:
    """This text as a reader, and which metagrammar accepted it — asked."""
    if not text.strip():
        return None
    for flavour in CANDIDATES:
        try:
            return compile_text(text, flavour=flavour), type(flavour).name
        except LexicError, RecursionError, ValueError:
            continue
    return None


class Reading:
    """A document read under a reader, and what each surface of it needs."""

    def __init__(self, reader: Path, document: Path) -> None:
        self.reader = reader
        self.document = document
        self.reader_text = reader.read_text()
        self.text = document.read_text()
        self.spans: list[Span] = []
        self.seconds = 0.0
        self.faithful = False
        self.words = ""
        self.flavour = ""

    def hold(self) -> None:
        """Read it. A refusal is a result, not an exception that escapes."""
        turned = turn(self.reader_text)
        if turned is None:
            self.words = "nothing compiles this as a reader"
            return
        machine, self.flavour = turned
        clock = time.perf_counter()
        try:
            model = machine.parse(self.text)
        except LexicError as refusal:
            self.seconds = time.perf_counter() - clock
            self.words = str(refusal)
            return
        self.seconds = time.perf_counter() - clock
        spelled, self.spans = fold(model)
        self.faithful = spelled == self.text

    def facets(self) -> list[Facet]:
        """Each surface, with the room it needs — measured, never assumed."""
        lines = self.text.split("\n")
        rules = self.reader_text.split("\n")
        deep = max((span.depth for span in self.spans), default=0) + 1
        return [
            Facet("reader", "plane", max(len(r) for r in rules), len(rules)),
            Facet("document", "plane", max(len(line) for line in lines), len(lines)),
            # the chart is as wide as the text is long, in columns of one char,
            # and as tall as the derivation is deep — it never fits, which is
            # why it scrubs a window over the text rather than showing it all
            Facet("derivation", "chart", 120, deep),
            Facet("spine", "stack", 48, deep),
        ]


class Opening:
    """A model waiting to be entered, and what it was called on the way in."""

    __slots__ = ("depth", "field", "model")

    def __init__(self, model: GrammarModel, field: str, depth: int) -> None:
        self.model = model
        self.field = field
        self.depth = depth


def fold(model: GrammarModel) -> tuple[str, list[Span]]:
    """Emit the model and record where each occurrence landed."""
    out: list[str] = []
    spans: list[Span] = []
    at = 0
    stack: list[object] = [Opening(model, "", 0)]
    while stack:
        node = stack.pop()
        if isinstance(node, Span):
            node.end = at
        elif isinstance(node, Opening):
            stack.extend(_enter(node, spans, at))
        elif isinstance(node, list):
            stack.extend(reversed(node))
        else:
            text = node if isinstance(node, str) else str(node)
            out.append(text)
            at += len(text)
    return "".join(out), spans


def _enter(opening: Opening, spans: list[Span], at: int) -> list[object]:
    """Open the span, push the parts, leave the span itself as the close."""
    span = Span(at, opening.depth, type(opening.model).__grammar__.name, opening.field)
    spans.append(span)
    work: list[object] = [span]
    for tag, part in reversed(GrammarModel.emit_parts(opening.model)):
        work.append(_part(part, tag or "", opening.depth + 1))
    return work


def _part(part: object, field: str, depth: int) -> object:
    """One emitted part as stack work — a model to enter, a run, or a string."""
    if isinstance(part, GrammarModel):
        return Opening(part, field, depth)
    if isinstance(part, (list, tuple)):
        return [_part(item, field, depth) for item in part]
    return str(part)


def read(reader: Path, document: Path) -> Reading:
    """One reading, held."""
    reading = Reading(reader, document)
    reading.hold()
    return reading
