"""The session — every reading, and what re-reads when one changes.

A session is a flat set of readings that name each other. The tree
everyone sees is not stored: it is what naming produces, which is why
plugging, unplugging and transpiling are all the same operation here —
changing which reading a reading names.

Re-reading is the only rule with any depth to it. When a reading
changes, everything that names it is read again, and so on downward.
That is the cascade, and it runs in dependency order rather than in the
order things were opened, so a text is never read by a stale reader.
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import Vocabulary
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAlphabet, IrMap, IrSelf, IrStr, IrTuple
from opsis.praxis.reading import (
    FOREIGN,
    Outcome,
    Params,
    Reader,
    Reading,
    Source,
    refusal_of,
)

__all__ = ["Session", "alphabets"]


def alphabets(node: object) -> list[str]:
    """Every encoding name a grammar asks to be read under.

    A grammar's own answer to "what vocabulary do you want", taken off
    its AST. ``unicode`` is excluded: it is always bound, and binding a
    tokenizer under it would mean reading a char grammar as tokens.

    :param node: A grammar AST, or anything else — a thing with no
        alphabets asks for none.
    """
    if not isinstance(node, IrSelf):
        return []
    out: list[str] = []
    stack: list[IrSelf] = [node]
    while stack:
        here = stack.pop()
        if isinstance(here, IrAlphabet) and str(here.encoding) != "unicode":
            name = str(here.encoding)
            if name not in out:
                out.append(name)
        stack.extend(here.children())
    return out


class Session:
    """Every reading opsis is holding, and the surfaces it can read with."""

    __slots__ = ("root", "readings", "surfaces", "_next")

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.readings: dict[str, Reading] = {}
        self.surfaces: dict[str, Reader] = {}
        self._next = 0

    # ── holding readings ──────────────────────────────────────────────

    def add(
        self,
        title: str,
        kind: str = "text",
        reader: str = "",
        source: Source = Source(),
    ) -> Reading:
        """Hold a new reading and read it.

        :param title: What it is called on screen.
        :param kind: What it turned out to be.
        :param reader: The ident or surface name that reads it.
        :param source: Its text, and where that text came from.
        """
        self._next += 1
        reading = Reading(f"r{self._next}", title, kind, reader)
        reading.text = source.text
        reading.params = Params(origin=source.origin)
        self.readings[reading.ident] = reading
        self.read(reading.ident)
        return reading

    def claim(self, ident: str) -> None:
        """Reserve a name a restored reading already carries.

        Thawing puts readings back under the names they were saved
        with, so the counter has to move past them or the next new node
        would take a name that is already on screen.
        """
        if ident.startswith("r") and ident[1:].isdigit():
            self._next = max(self._next, int(ident[1:]))

    def surface(self, reader: Reader) -> str:
        """Hold a reader that came from lexic rather than from a reading."""
        self.surfaces[reader.name] = reader
        return reader.name

    def drop(self, ident: str) -> Reading | None:
        """Remove a reading; whatever named it is read again without it.

        Removing is not unplugging: what named this reading keeps its
        text and is simply read by nothing until something else is
        named. Nothing is deleted on disk, ever.
        """
        gone = self.readings.pop(ident, None)
        if gone is None:
            return None
        for other in self.readings.values():
            if other.reader == ident:
                other.reader = ""
                self.read(other.ident)
        return gone

    def name_reader(self, ident: str, reader: str) -> None:
        """Say what reads a reading — the one gesture behind the tree."""
        reading = self._get(ident)
        if reader and reader == ident:
            raise UnsupportedConstructError("a reading cannot read itself")
        if reader and self._would_cycle(ident, reader):
            raise UnsupportedConstructError(
                "that would make a circle: the reader is already read by this one"
            )
        reading.reader = reader
        self.read(ident)

    def _would_cycle(self, ident: str, reader: str) -> bool:
        """Whether naming ``reader`` would close a loop back to ``ident``."""
        seen = reader
        while seen:
            if seen == ident:
                return True
            nxt = self.readings.get(seen)
            seen = nxt.reader if nxt is not None else ""
        return False

    def _get(self, ident: str) -> Reading:
        """The reading by that name, or a refusal naming it."""
        reading = self.readings.get(ident)
        if reading is None:
            raise UnsupportedConstructError(f"no reading called {ident!r}")
        return reading

    # ── reading, and everything that follows from it ──────────────────

    def reader_for(self, reading: Reading) -> Reader | None:
        """What reads this one — a surface lexic ships, or another reading."""
        if not reading.reader:
            return None
        surface = self.surfaces.get(reading.reader)
        if surface is not None:
            return surface
        other = self.readings.get(reading.reader)
        return other.as_reader() if other is not None else None

    def readers_of(self, ident: str) -> list[Reading]:
        """Every reading that depends on this one, however it names it.

        Being read by it and being bound to it are both dependencies, so
        both cascade: editing a vocabulary document re-reads the
        grammars bound to it, which is the whole point of a binding
        being an ident.
        """
        return [
            r
            for r in self.readings.values()
            if ident in (r.reader, r.params.bound) and r.ident != ident
        ]

    def bind(self, ident: str, vocabulary: str) -> None:
        """Say which reading's product is this one's vocabulary."""
        reading = self._get(ident)
        if vocabulary == ident:
            raise UnsupportedConstructError("a grammar cannot be its own vocabulary")
        reading.params = reading.params._replace(bound=vocabulary)
        self.read(ident)

    def vocabulary_for(self, reading: Reading, instance: object = None) -> Vocabulary:
        """The vocabulary a reading is bound to, resolved now.

        A binding to a reading that has since gone, or that no longer
        produces a vocabulary, is simply no binding — the grammar reads
        unbound and its node says what it is bound to, which is nothing.

        A tokenizer binds under its own name, which is not usually the
        name the grammar asks for: a grammar says ``IrAlphabet("tokens",
        …)`` and means "whatever vocabulary I am read with". So the
        tokenizer is also bound under every encoding name this grammar
        actually names — read off its own AST, never a list of names
        opsis knows.
        """
        held = self.readings.get(reading.params.bound)
        tokenizer = held.tokenizer if held is not None else None
        if tokenizer is None:
            return Vocabulary()
        wanted = alphabets(instance)
        registry = IrMap(*(IrTuple(IrStr(name), tokenizer) for name in wanted))
        return Vocabulary(tokenizer=tokenizer, registry=registry or None)

    def read(self, ident: str) -> None:
        """Read this one, then everything that names it, downward.

        A refusal is recorded and drawn, never raised at the caller: a
        text that does not parse is a state the session is allowed to be
        in, and the message is the interesting part.
        """
        reading = self._get(ident)
        reading.outcome = Outcome()
        reader = self.reader_for(reading)
        if reader is not None and reading.text:
            reading.outcome = self._both(reading, reader)
        for below in self.readers_of(ident):
            self.read(below.ident)

    def _both(self, reading: Reading, reader: Reader) -> Outcome:
        """The two readings of one text, in the order they depend on.

        A refusal in the first is a refusal, full stop: there is no
        second reading of a text that would not parse, and pretending
        otherwise would mean drawing a product built from nothing.
        """
        instance: object | None = None
        try:
            if reader.instance is not None:
                instance = reader.instance(reading.text)
            reading.params = reading.params._replace(
                vocabulary=self.vocabulary_for(reading, instance)
            )
            return Outcome(instance, self._built(reader, reading, instance))
        except FOREIGN as exc:
            return Outcome(instance, None, refusal_of(exc))

    def _built(self, reader: Reader, reading: Reading, instance: object) -> object:
        """The product — refined off the first reading where there is one."""
        if reader.refine is not None and instance is not None:
            return reader.refine(instance, reading.params)
        return reader.read(reading.text, reading.params)

    def edit(self, ident: str, text: str, params: Params | None = None) -> None:
        """Set a reading's input and re-read it and everything under it."""
        reading = self._get(ident)
        reading.text = text
        if params is not None:
            reading.params = params
        self.read(ident)

    def instance_of(self, reading: Reading) -> object | None:
        """The other reading of this text, where its reader offers one.

        A flavour reduces a grammar text to an AST AND compiles it; both
        are readings of one text, so both belong to one node rather than
        to two. This is what :meth:`read` already computed — asking for
        it must never be what triggers a ten-megabyte reduction.
        """
        return reading.instance
