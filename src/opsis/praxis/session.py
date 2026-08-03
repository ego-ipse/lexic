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

from lexic.exceptions import UnsupportedConstructError
from opsis.praxis.reading import Params, Reader, Reading, refusal_of

__all__ = ["Session"]


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
        text: str = "",
        origin: str = "",
    ) -> Reading:
        """Hold a new reading and read it."""
        self._next += 1
        reading = Reading(f"r{self._next}", title, kind, reader, text, origin)
        self.readings[reading.ident] = reading
        self.read(reading.ident)
        return reading

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
        """Every reading that names this one as its reader."""
        return [r for r in self.readings.values() if r.reader == ident]

    def read(self, ident: str) -> None:
        """Read this one, then everything that names it, downward.

        A refusal is recorded and drawn, never raised at the caller: a
        text that does not parse is a state the session is allowed to be
        in, and the message is the interesting part.
        """
        reading = self._get(ident)
        reading.instance = None
        reading.product = None
        reading.error = ""
        reader = self.reader_for(reading)
        if reader is not None and reading.text:
            try:
                self._both(reading, reader)
            except Exception as exc:  # a reader may be foreign code
                reading.error = refusal_of(exc)
        for below in self.readers_of(ident):
            self.read(below.ident)

    def _both(self, reading: Reading, reader: Reader) -> None:
        """The two readings of one text, in the order they depend on.

        A refusal in the first is a refusal, full stop: there is no
        second reading of a text that would not parse, and pretending
        otherwise would mean drawing a product built from nothing.
        """
        if reader.instance is not None:
            reading.instance = reader.instance(reading.text)
        if reader.refine is not None and reading.instance is not None:
            reading.product = reader.refine(reading.instance, reading.params)
            return
        reading.product = reader.read(reading.text, reading.params)

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
