"""The READING relation — (reader, document) → a value, and what it cost.

One relation kind among several, and the one atlas mistook for the program.
Chirality is computed here: a thing may stand as READER exactly when the
engine compiles it.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence

from facets import Ask, Facet, Plane
from lexic.compile import CompiledGrammar, compile_ast, compile_text
from lexic.exceptions import LexicError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir.flavour import IrFlavour
from lexic.ir.grammar.nodes import IrAst
from lexic.model import GrammarModel
from relate import DOCUMENT, KINDS, READER, Relation, Role, Thing, Value

__all__ = ["Reading", "Span", "fold", "metagrammar", "read_by", "turn"]

# Order is preference, not truth: the first that accepts wins, and being
# accepted by one is what "is a grammar" MEANS here.
CANDIDATES = (GBNF_FLAVOUR, ABNF_FLAVOUR, EBNF_FLAVOUR)


class Turn:
    """A thing turned into a reader, and whose grammar accepted it."""

    __slots__ = ("flavour", "machine")

    def __init__(self, machine: CompiledGrammar, flavour: IrFlavour | None) -> None:
        self.machine = machine
        self.flavour = flavour


_TURNED: dict[int, Turn | None] = {}
_METAS: dict[str, Value] = {}


def turn(thing: Thing) -> Turn | None:
    """This thing as a reader, or ``None``. Cached by object identity."""
    key = id(thing)
    if key not in _TURNED:
        _TURNED[key] = _compile(thing)
    return _TURNED[key]


def _compile(thing: Thing) -> Turn | None:
    """Ask the engine. Every refusal is a real answer, so none is logged."""
    if isinstance(thing, Value) and isinstance(thing.value, IrAst):
        return Turn(compile_ast(thing.value), None)
    text = thing.spelling()
    if not text.strip():
        return None
    for flavour in CANDIDATES:
        try:
            return Turn(compile_text(text, flavour=flavour), flavour)
        except LexicError, RecursionError, ValueError:
            continue
    return None


def metagrammar(flavour: IrFlavour) -> Value:
    """The flavour's own grammar, as a thing — the reader one level up."""
    name = type(flavour).name
    if name not in _METAS:
        _METAS[name] = Value(
            f"meta.{name}", f"the {name.upper()} metagrammar", flavour.grammar
        )
    return _METAS[name]


def read_by(thing: Thing) -> Value | None:
    """The metagrammar that accepts this thing's characters, as a thing."""
    turned = turn(thing)
    if turned is None or turned.flavour is None:
        return None
    return metagrammar(turned.flavour)


class Span:
    """One occurrence: a value, at a place, under a name."""

    __slots__ = ("depth", "end", "field", "rule", "start")

    def __init__(self, start: int, depth: int, rule: str, field: str) -> None:
        self.start = start
        self.end = start
        self.depth = depth
        self.rule = rule
        self.field = field


class Opening:
    """A model waiting to be entered, and what it was called on the way in."""

    __slots__ = ("depth", "field", "model")

    def __init__(self, model: GrammarModel, field: str, depth: int) -> None:
        self.model = model
        self.field = field
        self.depth = depth


def fold(model: GrammarModel) -> tuple[str, list[Span]]:
    """Emit the model and record where each occurrence landed.

    One traversal of the tagged stream ``to_text`` consumes, so spans cannot
    drift from the text.
    """
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
    """Open the span, push the parts, and leave the span itself as the close."""
    name = type(opening.model).__grammar__.name
    span = Span(at, opening.depth, name, opening.field)
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


class Reading(Relation):
    """A document, read under a reader — and the value that came out."""

    kind = "reading"
    slots = (READER, DOCUMENT)

    def __init__(self, rid: str, cast: Mapping[str, Thing]) -> None:
        super().__init__(rid, cast)
        self.value: Value | None = None
        self.spans: list[Span] = []
        self.seconds = 0.0
        self.faithful = False
        self.words = ""

    @classmethod
    def licenses(cls, role: Role, thing: Thing) -> bool:
        """Can it read, can it be read — both asked, neither declared."""
        if role is READER:
            return turn(thing) is not None
        return bool(thing.spelling())

    @classmethod
    def complete(cls, cast: Mapping[str, Thing]) -> Mapping[str, Thing] | None:
        """A document alone completes with whatever metagrammar accepts it."""
        if READER.name in cast and DOCUMENT.name in cast:
            return cast
        document = cast.get(DOCUMENT.name)
        if document is None:
            return None
        reader = read_by(document)
        return (
            None if reader is None else {DOCUMENT.name: document, READER.name: reader}
        )

    def label(self) -> str:
        return f"{self.cast[DOCUMENT.name].name} ⊳ {self.cast[READER.name].name}"

    def hold(self) -> None:
        """Read it. A refusal is a result, not an exception that escapes."""
        if self.held:
            return
        self.held = True
        turned = turn(self.cast[READER.name])
        text = self.cast[DOCUMENT.name].spelling()
        if turned is None:
            self.words = "this thing cannot stand as a reader — nothing compiles it"
            return
        clock = time.perf_counter()
        try:
            model = turned.machine.parse(text)
        except LexicError as refusal:
            self.words = str(refusal)
            self.seconds = time.perf_counter() - clock
            return
        self.seconds = time.perf_counter() - clock
        spelling, self.spans = fold(model)
        self.faithful = spelling == text
        self.value = Value(f"{self.rid}.value", f"{self.label()} — the value", model)

    def products(self) -> Mapping[str, Thing]:
        return {} if self.value is None else {"value": self.value}

    def verdict(self) -> str:
        """Round-trip fidelity, measured on this very text."""
        if self.words:
            return "fails the reader refused — see the document"
        state = "holds" if self.faithful else "fails"
        return f"{state} model.to_text() == document — {state}"

    def facets(self) -> Sequence[Facet]:
        """The four atlas earned, meaning here what they meant there."""
        reader = self.cast[READER.name]
        return [
            Plane(
                "reader",
                "the reader",
                "grammar is the ground truth",
                reader.spelling() or _spelled(reader),
            ),
            Plane(
                "document",
                "the document",
                "the text this reading is of",
                self.cast[DOCUMENT.name].spelling(),
            ),
            Chart("derivation", "the derivation", "text is the time axis", self),
            Stack("spine", "the spine", "what is open at the cursor", self),
        ]

    def arrangement(self, count: int) -> str:
        """The reader narrow, the document wide, the derived facets beside."""
        if count != 4:
            return super().arrangement(count)
        return "(h 0.24 0 (h 0.62 1 (v 0.58 2 3)))"


def _spelled(thing: Thing) -> str:
    """A value reader has no text of its own — spell it through its flavour."""
    turned = turn(thing)
    if turned is None:
        return ""
    return GBNF_FLAVOUR.apply(turned.machine.grammar)


class Chart(Facet):
    """The parse on the text axis — asked per cursor, never shipped whole."""

    kind = "chart"

    def __init__(self, name: str, title: str, note: str, reading: Reading) -> None:
        super().__init__(name, title, note)
        self.reading = reading

    def body(self) -> Sequence[str]:
        return [
            f"#SIZE {len(self.reading.spans)} "
            f"{len(self.reading.cast[DOCUMENT.name].spelling())}"
        ]

    def ask(self, query: Ask) -> str | None:
        """The spans that touch a window — a facet asks for what it can use."""
        low = int(query.get("from", "0"))
        high = int(query.get("to", "0")) or low + 400
        rows = [
            f"{s.start} {s.end} {s.depth} {s.rule} {s.field}"
            for s in self.reading.spans
            if s.start < high and s.end > low
        ]
        return f"#SPANS {len(rows)}\n" + "\n".join(rows) + "\n"


class Stack(Facet):
    """What is open at the cursor, and what just closed under it."""

    kind = "spine"

    def __init__(self, name: str, title: str, note: str, reading: Reading) -> None:
        super().__init__(name, title, note)
        self.reading = reading

    def ask(self, query: Ask) -> str | None:
        at = int(query.get("at", "0"))
        open_here = [s for s in self.reading.spans if s.start <= at < s.end]
        closed = [s for s in self.reading.spans if s.end == at]
        rows = [
            f"#OPEN {s.depth} {s.rule} {s.start} {s.end}"
            for s in sorted(open_here, key=lambda s: s.depth)
        ]
        rows += [f"#CLOSED {s.depth} {s.rule} {s.start} {s.end}" for s in closed[-6:]]
        return "\n".join(rows) + "\n"


KINDS[Reading.kind] = Reading
