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
from unicodedata import east_asian_width

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import LexicError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR, get_flavour
from lexic.model import GrammarModel

from praxis.graph import digest

__all__ = [
    "Facet",
    "ReaderProbe",
    "Reading",
    "Span",
    "as_written",
    "probe",
    "profile",
    "read",
    "read_up",
    "turn",
    "upward",
]

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


class ReaderProbe:
    """One candidate metagrammar's answer, accepted or refused verbatim."""

    __slots__ = ("flavour", "machine", "words")

    def __init__(
        self,
        flavour: str,
        machine: CompiledGrammar | None,
        words: str = "",
    ) -> None:
        self.flavour = flavour
        self.machine = machine
        self.words = words

    @property
    def accepted(self) -> bool:
        return self.machine is not None


def probe(text: str) -> tuple[ReaderProbe, ...]:
    """Ask every pure grammar flavour; preserve every engine answer."""
    out: list[ReaderProbe] = []
    for flavour in CANDIDATES:
        name = type(flavour).name
        try:
            out.append(ReaderProbe(name, compile_text(text, flavour=flavour)))
        except (LexicError, RecursionError, ValueError) as refusal:
            out.append(ReaderProbe(name, None, str(refusal)))
    return tuple(out)


def turn(text: str, flavour: str = "") -> tuple[CompiledGrammar, str] | None:
    """Return one reader only when the question has one explicit answer."""
    tested = probe(text)
    accepted = [answer for answer in tested if answer.accepted]
    if flavour:
        chosen = next((answer for answer in accepted if answer.flavour == flavour), None)
        return (chosen.machine, chosen.flavour) if chosen and chosen.machine else None
    if len(accepted) == 1 and accepted[0].machine is not None:
        return accepted[0].machine, accepted[0].flavour
    return None


class Reading:
    """A document read under a reader, and what each surface of it needs."""

    def __init__(self, reader: Path, document: Path, flavour: str = "") -> None:
        self.reader = reader
        self.document = document
        self.reader_text = reader.read_text()
        self.text = document.read_text()
        self.flavour = flavour.casefold()
        self.offers: tuple[str, ...] = ()
        self.probes: tuple[ReaderProbe, ...] = ()
        self.spans: list[Span] = []
        self.seconds = 0.0
        self.faithful = False
        self.words = ""
        # what the reader is CALLED: a metagrammar is not a file, so the
        # label cannot come from a path without lying about the pairing
        self.reader_name = reader.name

    @property
    def identity(self) -> str:
        """This relation's address: the ordered reader and document content."""
        reader = digest("text", self.reader_text)
        document = digest("text", self.text)
        return digest("reading", "read", self.flavour or "unresolved", reader, document)

    def __eq__(self, other: object) -> bool:
        """Equal content under the same explicit reader is one relation."""
        return isinstance(other, Reading) and self.identity == other.identity

    @property
    def ambiguous(self) -> bool:
        """Whether more than one metagrammar accepted and none was cast."""
        return not self.flavour and len(self.offers) > 1

    def hold(self) -> None:
        """Read it. A refusal is a result, not an exception that escapes."""
        self.spans = []
        self.seconds = 0.0
        self.faithful = False
        self.words = ""
        self.probes = probe(self.reader_text)
        accepted = [answer for answer in self.probes if answer.accepted]
        self.offers = tuple(answer.flavour for answer in accepted)
        chosen = next(
            (
                answer
                for answer in accepted
                if self.flavour and answer.flavour == self.flavour
            ),
            None,
        )
        if not self.flavour and len(accepted) == 1:
            chosen = accepted[0]
            self.flavour = chosen.flavour
        elif not self.flavour and len(accepted) > 1:
            names = " and ".join(name.upper() for name in self.offers)
            self.words = f"reader accepted by {names} — choose one"
            return
        if chosen is None or chosen.machine is None:
            refused = next(
                (
                    answer.words
                    for answer in self.probes
                    if answer.flavour == self.flavour and answer.words
                ),
                next((answer.words for answer in self.probes if answer.words), ""),
            )
            self.words = refused
            return
        clock = time.perf_counter()
        try:
            model = chosen.machine.parse(self.text)
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
            Facet(
                "grammar",
                "plane",
                wide_rules,
                len(rules),
                title="THE READER · grammar is the ground truth",
                column="reader",
            ),
            Facet(
                "document",
                "plane",
                wide_lines,
                len(lines),
                title="THE DOCUMENT · real text — select it",
                column="document",
            ),
            # The chart shows a WINDOW over the text, so what it needs is the
            # window it scrubs: as many columns as the longest line it must
            # place, and one row per depth. A typed 120 was the last guess
            # left in a build that measures everything else.
            Facet(
                "chart",
                "chart",
                max(wide_lines, deep * 4),
                deep,
                title="THE DERIVATION · text is the time axis",
                column="derivation",
                relation="stacked",
            ),
            # the spine is read AT the cursor the chart is scrubbing, so it
            # shares that column rather than taking one of its own
            Facet(
                "spine",
                "stack",
                48,
                max(4, deep // 2),
                title="THE SPINE",
                column="derivation",
                relation="stacked",
            ),
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
    if not reading.flavour:
        return None
    return (str(reading.reader), f"the {reading.flavour.upper()} metagrammar")


def read_up(below: Reading) -> Reading | None:
    """The rung above: this reader, read as a document by its metagrammar.

    The metagrammar is not a file — it is the flavour's own grammar — so the
    reading is built with its SPELLING as the reader text. Chirality already
    named this pair; here it is held.
    """
    flavour = below.flavour
    if not flavour:
        return None
    above = Reading(below.reader, below.reader, flavour)
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
