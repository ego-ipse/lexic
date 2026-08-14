"""Editing — an edit is a RE-READING, not a patch on the value.

Text is primary; the model is only the grammar's account of what the text
says. So a commit splices characters and reads again, and everything derived
re-derives or nothing changes.

The correction this carries from the build before: a refused re-read reports
WHERE derivation died, measured off the kernel's own cursor, never scraped
out of an exception's prose — and it restores the document, because a reading
that kept its old spans beside new text is the one lie the instrument rests
on not telling.
"""

from __future__ import annotations

from kairos.parse import Clock
from praxis.reading import Reading

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.pda.core.errors import PdaFail

__all__ = ["Retype", "frontier", "retype"]


class Retype:
    """What a re-reading did, and where it stopped if it stopped."""

    __slots__ = ("pos", "seconds", "state", "words")

    def __init__(
        self, state: str, seconds: float = 0.0, pos: int = -1, words: str = ""
    ) -> None:
        self.state = state
        self.seconds = seconds
        self.pos = pos
        self.words = words

    def line(self) -> str:
        if self.state == "refused":
            return f"refused at {self.pos} — {self.words}"
        return f"read again in {self.seconds:.2f}s"


def frontier(reading: Reading, text: str) -> int:
    """Where the predictive route stopped — the kernel's own cursor, measured."""
    try:
        machine = compile_text(reading.reader_text, flavour=reading.flavour or "gbnf")
    except LexicError:
        return -1
    kernel = Clock(machine.pda_tables(), text, machine.fold)
    try:
        kernel.run()
    except PdaFail:
        return kernel.pos
    except LexicError:
        return -1
    return -1


def retype(reading: Reading, start: int, end: int, put: str) -> Retype:
    """Splice the characters and read again. The value follows the text."""
    was = reading.text
    reading.text = was[:start] + put + was[end:]
    reading.spans = []
    reading.words = ""
    reading.hold()
    if reading.words:
        stop = frontier(reading, reading.text)
        words = reading.words
        reading.text = was
        reading.spans = []
        reading.words = ""
        reading.hold()
        return Retype("refused", pos=stop, words=words)
    return Retype("read", seconds=reading.seconds)
