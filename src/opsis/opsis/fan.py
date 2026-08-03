"""What a node offers — eight windows, each holding its own parts.

A node used to wear twenty-four readings. Most of them were one thing
said twice: a grammar's rules and its railroad are one shape drawn two
ways, an instance and a product are one tree, a floor and a chart and
an execution are one parse. So they are one window each now, with the
parts inside opening when they are wanted.

The table is the point. Each row says what a window is called, what has
to be TRUE of a reading for it to exist, and which parts it holds — so
a window is absent because its own test says so, and a part is absent
because the reading has not got it. Nothing here is a branch somebody
could forget to update.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from lexic.compile import CompiledGrammar
from lexic.model import GrammarModel
from opsis.opsis.pane import artefact
from opsis.praxis.deeds.acts import deeds
from opsis.praxis.reading import Reading
from opsis.praxis.session import Session, alphabets

__all__ = [
    "OFFERS",
    "PARTS",
    "Fan",
    "Offer",
    "Part",
    "fan",
    "fanned",
    "offered",
    "parts_of",
]


class Fan(NamedTuple):
    """What the table gets to look at — a reading, and what read it."""

    reading: Reading
    read_by: CompiledGrammar | None = None
    grammar: CompiledGrammar | None = None


Test = Callable[[Fan], bool]
"""What has to be true of a reading for something to be offered."""


class Part(NamedTuple):
    """One section of a window, and when it is in there."""

    kind: str
    label: str
    why: str
    when: Test


class Offer(NamedTuple):
    """One window a node can open, and when it can."""

    kind: str
    label: str
    when: Test


def _grammar(at: Fan) -> bool:
    """Whether this reading IS a grammar, however it came to be one."""
    return at.grammar is not None


def _read(at: Fan) -> bool:
    """Whether something above actually read this one."""
    return at.read_by is not None


def _model(at: Fan) -> bool:
    """Whether what came back is a parsed model."""
    return isinstance(at.reading.product, GrammarModel)


def _built(at: Fan) -> bool:
    """Whether something came back that is not itself a grammar."""
    return at.reading.product is not None and at.reading.compiled is None


def _vocabulary(at: Fan) -> bool:
    """Whether this reading produced a vocabulary."""
    return at.reading.tokenizer is not None


def _docked(at: Fan) -> bool:
    """Whether a vocabulary is docked to this grammar."""
    return at.grammar is not None and at.grammar.tokens.tokenizer is not None


def _segmented(at: Fan) -> bool:
    """Whether the grammar above reads this text as tokens."""
    return at.read_by is not None and at.read_by.tokens.segmented


def _flavour(at: Fan) -> bool:
    """Whether this reading produced a reader."""
    return at.reading.flavour is not None


def _wants(at: Fan) -> bool:
    """Whether this grammar names an encoding nothing is bound under."""
    return bool(alphabets(at.reading.instance))


def _always(_at: Fan) -> bool:
    """In whenever its window is."""
    return True


OFFERS: tuple[Offer, ...] = (
    Offer("text", "text", _always),
    Offer("shape", "shape", _grammar),
    Offer(
        "built",
        "built ▲",
        lambda a: a.reading.product is not None or a.reading.instance is not None,
    ),
    Offer("parse", "parse", _read),
    Offer("compile", "compile", _grammar),
    Offer("tokens", "tokens", lambda a: _grammar(a) or _vocabulary(a)),
    Offer("bench", "bench", lambda a: _grammar(a) or _read(a)),
    Offer("meta", "meta", lambda a: _flavour(a) or _grammar(a) or not a.reading.reader),
)
"""The windows a node wears. Eight, and each one earns its place."""


PARTS: dict[str, tuple[Part, ...]] = {
    "shape": (
        Part("rules", "rules", "by distance from the start", _grammar),
        Part("railroad", "railroad", "every rule's track", _grammar),
        Part("binding", "binding", "rule → class and field names", _grammar),
        Part("fold", "fold", "how an instance is built", _grammar),
    ),
    "built": (
        Part(
            "instance",
            "what it built",
            "the tree, beside its text",
            lambda a: a.reading.product is not None or a.reading.instance is not None,
        ),
        Part(
            "space", "its shape", "the same tree as a space — depth and width", _model
        ),
        Part("semantic", "semantic", "noise dimmed, never removed", _model),
        Part("regrammar", "its grammar", "back to the surface it came from", _model),
        Part("reader", "read by", "the grammar above it", _read),
    ),
    "parse": (
        Part("floor", "the floor", "measured claims about this parse", _read),
        Part("execution", "what ran", "the runtime's own record", _read),
        Part("chart", "chart", "columns of items", _read),
        Part("forest", "forest", "every derivation, packed", _read),
        Part("derivations", "derivations", "enumerated — this one can be slow", _read),
    ),
    "compile": (
        Part("pipeline", "stages", "what each pass changed", _grammar),
        Part("runs", "runs", "the lexical layer it derives", _grammar),
        Part("module", "module", "the importable twin", _grammar),
        Part("doc", "document", "the emission, at a width you drag", _grammar),
        Part("tables", "tables", "the predictive artefact", _grammar),
        Part("analysis", "verdicts", "what the analysis decided", _grammar),
    ),
    "tokens": (
        Part("tokens", "binding", "bound, segments, unresolved", _grammar),
        Part("plug", "plug ⊕", "what it needs, and what could be it", _wants),
        Part("bound", "bound to", "the vocabulary docked here", _docked),
        Part("vocabulary", "vocabulary", "what this reading produced", _vocabulary),
        Part("segmentation", "its tokens", "where this text was cut", _segmented),
    ),
    "bench": (
        Part("carve", "template", "extract the paths you name", _grammar),
        Part("constrain", "constrain", "what may come next, at a prefix", _docked),
        Part("resume", "resume", "a chart that grows, and winds back", _grammar),
    ),
    "meta": (
        Part("flavour", "what it IS", "metadata and tables", _flavour),
        Part("dispatch", "its tables", "everything it dispatches on", _flavour),
        Part("lanes", "lanes ≅", "is anything here the same language", _grammar),
        Part("transpile", "transpile", "this grammar in every other surface", _grammar),
        Part("shadow", "shadows ⚠", "who else answers to this name", _flavour),
        Part(
            "registry",
            "the registry",
            "what a product's window comes from",
            lambda a: not a.reading.reader,
        ),
    ),
}
"""Window → the parts inside it, and when each part is there.

A window whose parts all test false is still offered when its own test
passes — it says it has nothing, which is a fact about the reading. A
part that tests false is simply not in there.
"""


def fanned(session: Session, reading: Reading) -> Fan:
    """What the table gets to look at, for this reading."""
    above = session.readings.get(reading.reader)
    return Fan(
        reading,
        artefact(above) if above is not None and reading.text else None,
        artefact(reading),
    )


def offered(at: Fan, doable: tuple[tuple[str, str], ...] = ()) -> list[Offer]:
    """Every window this reading has, its deeds folded in as one more."""
    out = [offer for offer in OFFERS if offer.when(at)]
    if doable:
        out.append(Offer("do", "do", _always))
    return out


def parts_of(at: Fan, window: str) -> list[Part]:
    """The parts inside one window that this reading actually has."""
    return [part for part in PARTS.get(window, ()) if part.when(at)]


def fan(session: Session, reading: Reading) -> list[tuple[str, str]]:
    """The windows this one offers — what a ring wears."""
    at = fanned(session, reading)
    doable = tuple((d.name, d.label) for d in deeds(reading))
    return [(o.kind, o.label) for o in offered(at, doable)]
