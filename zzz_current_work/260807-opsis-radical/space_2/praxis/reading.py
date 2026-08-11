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
from unicodedata import east_asian_width
from pathlib import Path

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import LexicError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR, get_flavour
from lexic.model import GrammarModel

from praxis.memory import Memory

__all__ = [
    "Facet",
    "Reading",
    "reader_of",
    "ruledefs",
    "Span",
    "as_written",
    "profile",
    "read",
    "read_up",
    "upward",
]

CANDIDATES = (GBNF_FLAVOUR, ABNF_FLAVOUR, EBNF_FLAVOUR)

# a rule head, in any of the three notations — where a name is DEFINED
HEAD = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")


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

    __slots__ = ("column", "kind", "name", "relation", "tall", "title", "wide")

    def __init__(
        self,
        name: str,
        kind: str,
        wide: int,
        tall: int,
        title: str = "",
        column: str = "",
        relation: str = "beside",
    ) -> None:
        self.name = name
        self.kind = kind
        self.wide = wide
        self.tall = tall
        # what it is CALLED on screen, and where it lives. Both belong here:
        # the leaf should be able to draw this instrument without knowing
        # that a thing called "grammar" is the reader, or that the relations
        # are a second view of it.
        self.title = title or name
        self.column = column or name
        self.relation = relation

    def wire(self) -> str:
        return (
            f"#FACET {self.name} {self.kind} needs {self.wide} {self.tall} "
            # the title runs last because it is the only field with spaces
            f"in {self.column} {self.relation} {self.title}"
        )


def ruledefs(text: str) -> list[tuple[str, int, int]]:
    """Where each rule lives in the reader text — line ranges, addressable."""
    heads = [
        (m.group(1), i)
        for i, line in enumerate(text.split("\n"))
        if (m := HEAD.match(line))
    ]
    out = []
    for place, (name, start) in enumerate(heads):
        stop = heads[place + 1][1] - 1 if place + 1 < len(heads) else text.count("\n")
        out.append((name, start, stop))
    return out


# The same language, at three moments of the pipeline. None of them is more
# true than the others: a grammar as WRITTEN, in its canonical normal form,
# and as codegen cut it for the parser. The views disagreed because each was
# drawing a different one — the automaton is built from the codegen form, so
# a choice it makes has no node in the source form at all.


READERS: Memory[CompiledGrammar | None] = Memory()


def reader_of(reading: Reading) -> CompiledGrammar | None:
    """This reading's reader, compiled — or nothing, if nothing reads it."""
    return READERS.once(reading.reader_text, lambda: _compile(reading))


def _compile(reading: Reading) -> CompiledGrammar | None:
    """Compile it, once. A refusal is a result, not an exception that escapes."""
    try:
        return compile_text(reading.reader_text, flavour=reading.flavour or "gbnf")
    except LexicError, RecursionError, ValueError:
        return None


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
        self.stamp = 0
        self.seconds = 0.0
        self.faithful = False
        self.words = ""
        self.flavour = ""
        # what the reader is CALLED: a metagrammar is not a file, so the
        # label cannot come from a path without lying about the pairing
        self.reader_name = reader.name

    def hold(self) -> None:
        """Read it. A refusal is a result, not an exception that escapes."""
        self.stamp += 1
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


def columns(line: str) -> int:
    """How many terminal columns this line occupies, wide glyphs counted twice."""
    return sum(2 if east_asian_width(ch) in "WF" else 1 for ch in line)


def _most(lines: list[str]) -> int:
    """The width nine lines in ten fit inside — not the longest.

    One 300-character rule would otherwise starve every other surface to feed
    an outlier nobody reads in full.

    Width is COLUMNS, not characters: a wide glyph takes two, so a CJK
    grammar would otherwise under-report what it needs by up to half.
    ``unicodedata`` already knows which are which, so no table of ours is
    needed.
    """
    widths = sorted(columns(line) for line in lines) or [0]
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


def read_up(below: Reading) -> Reading | None:
    """The rung above: this reader, read as a document by its metagrammar.

    The metagrammar is not a file — it is the flavour's own grammar — so the
    reading is built with its SPELLING as the reader text. Chirality already
    named this pair; here it is held.
    """
    turned = turn(below.reader_text)
    if turned is None:
        return None
    machine, flavour = turned
    above = Reading(below.reader, below.reader)
    above.reader_name = f"the {flavour.upper()} metagrammar"
    above.reader_text = get_flavour(flavour).apply(get_flavour(flavour).grammar)
    above.text = below.reader_text
    above.hold()
    return above


def read(reader: Path, document: Path) -> Reading:
    """One reading, held."""
    reading = Reading(reader, document)
    reading.hold()
    return reading


def profile(reading: Reading, buckets: int = 120) -> list[int]:
    """The shape of a reading across its document — how deep it runs, where.

    The MEAN depth of what opens in each stretch, not the deepest: one
    deeply-nested value in a bucket makes the maximum say 9 everywhere, and
    a bar chart of nines is a rectangle. The mean moves with the document,
    which is the only reason to draw it.
    """
    if not reading.spans or not reading.text:
        return []
    size = max(1, len(reading.text) // buckets)
    total = [0] * (len(reading.text) // size + 1)
    count = [0] * len(total)
    for span in reading.spans:
        at = min(span.start // size, len(total) - 1)
        total[at] += span.depth
        count[at] += 1
    means = [t / n if n else 0.0 for t, n in zip(total, count)]
    top = max(means) or 1.0
    return [round(9 * mean / top) for mean in means]
