"""The chain — every reading this one implies, and none of them parsed yet.

The map before this one drew relation instances as cards and called the
column index a stratum; both were guesses dressed as facts. Here a rung is
what it is: a pair that WOULD be a reading, named because chirality already
answered, and held only when someone enters it.

A thing's stratum is its distance from the document you started on, not its
position in a row — two things read at the same depth are the same stratum
however many columns sit between them.
"""

from __future__ import annotations

from pathlib import Path

from praxis.reading import Reading, upward

__all__ = ["Rung", "chain"]

CEILING = 8


class Rung:
    """One reading the chain implies: who reads what, and at what depth."""

    __slots__ = ("document", "level", "reader", "visited")

    def __init__(self, document: str, reader: str, level: int, visited: bool) -> None:
        self.document = document
        self.reader = reader
        self.level = level
        self.visited = visited

    def line(self) -> str:
        seen = "visited" if self.visited else "not yet visited — entering builds it"
        return f"{self.level} {self.document} ⊳ {self.reader} · {seen}"


def chain(reading: Reading) -> list[Rung]:
    """The ladder this reading implies, climbed by asking, never by listing.

    Each rung is named from the one below: the reader of a reading is the
    document of the next, and who reads THAT is a question chirality already
    answers. Nothing is parsed to build this — the climb stops when a text
    reads itself, which is the fixpoint, or at the ceiling.
    """
    rungs = [Rung(Path(reading.document).name, Path(reading.reader).name, 0, True)]
    step = upward(reading)
    level = 1
    while step is not None and level < CEILING:
        document, reader = step
        rungs.append(Rung(Path(document).name, reader, level, False))
        if Path(document).name == reader:
            break  # a text read by itself: the fixpoint
        step = None  # the rung above is named, not opened
        level += 1
    return rungs
