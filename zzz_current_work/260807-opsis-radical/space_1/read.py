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

import re
import time
from pathlib import Path

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import LexicError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.model import GrammarModel

__all__ = ["Facet", "Reading", "Span", "as_written", "read", "upward"]

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
        wide_rules = _most(rules)
        wide_lines = _most(lines)
        deep = max((span.depth for span in self.spans), default=0) + 1
        # named as the LEAF names them: a tree whose leaves nothing recognises
        # is silently dropped, and the measured layout never reaches the screen
        return [
            Facet("grammar", "plane", wide_rules, len(rules)),
            Facet("document", "plane", wide_lines, len(lines)),
            # The chart shows a WINDOW over the text, so what it needs is the
            # window it scrubs: as many columns as the longest line it must
            # place, and one row per depth. A typed 120 was the last guess
            # left in a build that measures everything else.
            Facet("chart", "chart", max(wide_lines, deep * 4), deep),
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


def _most(lines: list[str]) -> int:
    """The width nine lines in ten fit inside — not the longest.

    One 300-character rule would otherwise starve every other surface to feed
    an outlier nobody reads in full.

    KNOWN GAP: this counts CHARACTERS, and a wide glyph takes two columns.
    A CJK grammar (japanese.gbnf) therefore under-reports what it needs by up
    to half. Fixing it means an east-asian width table; until then the number
    is honest about what it measures and wrong about what it implies, which
    is worth saying out loud rather than discovering on screen.
    """
    widths = sorted(len(line) for line in lines) or [0]
    return max(24, widths[min(len(widths) - 1, int(len(widths) * 0.9))])


HOISTED = re.compile(r"^(.*)-(?:item|arm)\d*$")


def as_written(rules: list[tuple[str, int, int]], name: str) -> str:
    """This rule, spelled the way the GRAMMAR spells it.

    The engine folds (``json-text``) where the text says ``JSON-text``, and
    co-selection is a name match — so the folded name lights nothing. A
    codegen piece (``<rule>-item``, ``<rule>-arm<N>``) is a part cut out of a
    rule, so it lights the rule it came from, by the namer's own inverse.
    """
    written = {n.casefold(): n for n, _, _ in rules}
    said = written.get(name.casefold())
    if said is not None:
        return said
    cut = HOISTED.match(name)
    return as_written(rules, cut.group(1)) if cut else name


def upward(reading: Reading) -> tuple[str, str] | None:
    """The reading one level up: this reader, read as a document.

    Chirality is already computed — the reader compiled, so something read
    it. Going up is not a level, it is the same question asked of the other
    text: who reads THIS one. Returns the pair, never a parse: entering it
    is what parses, so an unvisited rung costs nothing.
    """
    turned = turn(reading.reader_text)
    if turned is None:
        return None
    return (str(reading.reader), f"the {turned[1].upper()} metagrammar")


def read(reader: Path, document: Path) -> Reading:
    """One reading, held."""
    reading = Reading(reader, document)
    reading.hold()
    return reading
