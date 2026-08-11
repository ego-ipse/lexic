"""The session — what the hand has done, and what each gesture means.

A pixel becomes an offset here, a click becomes a cursor, a tick becomes
time passing. The leaf posts what happened and never what it meant.
"""

from __future__ import annotations

from praxis.reading import Reading

__all__ = ["Session"]


class Session:
    """What the hand has done so far — the only state there is."""

    reading: Reading
    at: float = 0.0
    reader_top: int = 0
    doc_top: int = 0
    playing: bool = False
    generation: int = 1

    @classmethod
    def gesture(cls, said: str, wide: int, tall: int) -> None:
        """One gesture, applied. The leaf knows none of this arithmetic."""
        word, _, rest = said.strip().partition(" ")
        length = len(cls.reading.text)
        if word == "point":
            # a point in the derivation is a time; the picture's own pitch
            # is known here, so the leaf never converts pixels to offsets
            parts = rest.split()
            if len(parts) == 2 and parts[0].lstrip("-").isdigit():
                x = int(parts[0])
                left = wide * 0.34 + wide * 0.32
                pitch = 5.0
                window = max(8, int((wide - left - 20) / pitch))
                start = max(
                    0, min(int(cls.at) - int(window * 0.6), max(0, length - window))
                )
                if x >= left:
                    cls.at = max(0.0, min(start + (x - left - 10) / pitch, length))
        elif word == "at":
            kind, _, address = rest.partition(" ")
            if kind == "span" and ":" in address:
                cls.at = float(address.split(":")[0])
            elif kind == "line" and address.isdigit():
                cls.doc_top = int(address)
        elif word == "step":
            cls.at = max(0.0, min(cls.at + float(rest or 1), length))
        elif word == "go":
            cls.at = float(length if rest == "end" else 0)
        elif word == "play":
            cls.playing = not cls.playing
        elif word == "tick" and cls.playing:
            cls.at = min(cls.at + length / 90, length)
            cls.playing = cls.at < length
