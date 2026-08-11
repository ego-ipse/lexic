"""The session — what the hand has done, and what each gesture means.

A pixel becomes an offset here, a click becomes a cursor, a tab becomes the
surface on show. The leaf posts what happened and never what it meant.
"""

from __future__ import annotations

from praxis.reading import Reading

__all__ = ["Session"]


class Session:
    """One reading, and how the hand is looking at it."""

    __slots__ = (
        "at",
        "clock",
        "doc_top",
        "graph",
        "pitch",
        "generation",
        "playing",
        "rail_top",
        "reader_top",
        "reading",
        "surface",
        "yaw",
    )

    def __init__(self, reading: Reading) -> None:
        self.reading = reading
        self.at = 0.0
        self.playing = False
        self.generation = 1
        self.surface = "derivation"
        self.clock = "model"
        self.graph = "flat"
        self.yaw = 0.6
        self.pitch = 0.35
        self.reader_top = 0
        self.doc_top = 0
        self.rail_top = 0

    def gesture(self, said: str) -> None:
        """One gesture, applied."""
        # a chip that stands for a keystroke says so — it carries the gesture
        # it means, spaces written as ~ so one line stays one gesture
        word, _, rest = said.strip().replace("~", " ").partition(" ")
        if word == "do":
            self.gesture(rest)
            return
        length = len(self.reading.text)
        kind, _, address = rest.partition(" ")
        if word == "at" and kind == "span" and ":" in address:
            self.at = float(address.split(":")[0])
        elif word == "at" and kind == "surface":
            self.surface = address or rest
        elif word == "at" and kind == "clock":
            self.clock = address or rest
        elif word == "at" and kind == "graph":
            self.graph = address or rest
        elif word == "spin":
            dx, _, dy = rest.partition(" ")
            self.yaw += float(dx or 0) / 160
            self.pitch = max(-1.4, min(1.4, self.pitch + float(dy or 0) / 200))
        elif word == "at" and kind in ("line", "readerline") and address.isdigit():
            if kind == "line":
                self.doc_top = int(address)
            else:
                self.reader_top = int(address)
        elif word == "at" and kind == "rule":
            self.at = next(
                (
                    float(span.start)
                    for span in self.reading.spans
                    if span.rule.casefold() == address.casefold()
                    and span.start >= self.at
                ),
                self.at,
            )
        elif word == "scroll":
            which, _, by = rest.partition(" ")
            step = int(by) if by.lstrip("-").isdigit() else 0
            if which == "grammar":
                self.reader_top = max(0, self.reader_top + step * 3)
            elif which == "document":
                self.doc_top = max(0, self.doc_top + step * 3)
            elif which == "railroad":
                self.rail_top = max(0, self.rail_top + step * 24)
        elif word == "step":
            self.at = max(0.0, min(self.at + float(rest or 1), length))
        elif word == "go":
            self.at = float(
                length if rest == "end" else (int(rest) if rest.isdigit() else 0)
            )
        elif word == "play":
            self.playing = not self.playing
        elif word == "tick" and self.playing:
            self.at = min(self.at + length / 90, length)
            self.playing = self.at < length
