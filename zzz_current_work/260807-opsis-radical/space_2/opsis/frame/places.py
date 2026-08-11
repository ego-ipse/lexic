"""A PLACE — a room the reading holds, drawn.

`opsis.rooms` has written these since the first build: the rules by what they
account for, one rule with everything it is, the machine, the artefacts, and
any value as the value it IS. Every one existed on the wire with nothing
pointing at it, which is how a whole capability stays built and unseen. The
strata's doors point at them now, and this draws what they say.

A room is sections — a title, facts as pairs, doors as a list, a refusal —
and it takes the work area the way the strata does, because it is not a facet
of the reading either.
"""

from __future__ import annotations

from opsis.frame.marks import ROW, Frame
from opsis.frame.tones import runs

__all__ = ["draw", "read"]

PAD = 34.0


class Section:
    """One part of a room: what kind it is, and the lines it holds."""

    __slots__ = ("kind", "lines")

    def __init__(self, kind: str, lines: list[str]) -> None:
        self.kind = kind
        self.lines = lines


def read(wire: str) -> tuple[str, str, str, list[Section]]:
    """A room as it was written — its id, its kind, what it is, its sections."""
    pid = kind = says = ""
    out: list[Section] = []
    lines = wire.split("\n")
    at = 0
    while at < len(lines):
        line = lines[at]
        if line.startswith("#PLACE "):
            parts = line.split(" ")
            pid = parts[1] if len(parts) > 1 else ""
            kind = parts[2] if len(parts) > 2 else ""
            says = " ".join(parts[3:])
        elif line.startswith("#SEC "):
            parts = line.split(" ")
            count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            out.append(Section(parts[1], lines[at + 1 : at + 1 + count]))
            at += count
        at += 1
    return pid, kind, says, out


def _title(said: Frame, section: Section, _wide: int, y: float) -> float:
    for line in section.lines:
        said.text(PAD, y, "ink", line)
        y += ROW + 4
    return y


def _kv(said: Frame, section: Section, wide: int, y: float) -> float:
    """Facts as pairs — the name on the left, what it is on the right."""
    keys = [line.split("\t")[0] for line in section.lines]
    step = max((runs("fsub", key) for key in keys), default=0.0) + 24
    for line in section.lines:
        key, _, value = line.partition("\t")
        said.text(PAD, y, "fsub", key)
        said.text(PAD + step, y, "ink", value, wide - PAD * 2 - step)
        y += ROW
    return y


def _list(said: Frame, section: Section, wide: int, y: float) -> float:
    """Doors — each one a place this room opens onto."""
    for line in section.lines:
        label, _, pid = line.partition("\t")
        said.line(PAD, y - 13, PAD, y + 5, "cool")
        said.text(PAD + 12, y, "cool" if pid else "ink", label, wide - PAD * 2 - 20)
        if pid:
            said.hit(
                PAD, y - 14, wide - PAD * 2, ROW, "place", pid.removeprefix("place:")
            )
        y += ROW + 2
    return y


def _refusal(said: Frame, section: Section, wide: int, y: float) -> float:
    """A room nobody authored says so, in place — in the words it has."""
    for line in section.lines:
        said.text(PAD, y, "red", line, wide - PAD * 2)
        y += ROW
    return y


def _unbuilt(said: Frame, section: Section, _wide: int, y: float) -> float:
    """A section this frame draws no shape for — named, never silently dropped.

    The raising default, said on screen: an unauthored kind draws its own
    name, so coverage is visible rather than blank.
    """
    said.text(PAD, y, "dimmer", f"[{section.kind}] — this frame draws no shape for it")
    return y + ROW


DRAWN = {
    "title": _title,
    "kv": _kv,
    "list": _list,
    "refusal": _refusal,
}


def draw(said: Frame, wire: str, wide: int, tall: int) -> None:
    """The room, whole — its name, its facts, and the doors it opens onto."""
    pid, kind, says, sections = read(wire)
    said.box(0, 0, wide, tall, "field")
    said.text(PAD, 38, "chip", kind.upper(), face="chip")
    at = PAD + runs("chip", kind) + 18
    said.text(at, 38, "title", pid)
    said.text(at + runs("title", pid) + 16, 38, "fsub", says, wide - at - 220)
    said.line(0, 56, wide, 56, "hair")
    said.text(wide - PAD, 38, "cool", "‹ back", anchor="r", face="chip")
    said.hit(wide - PAD - 60, 24, 64, 20, "strata", "on")

    y = 92.0
    for section in sections:
        y = DRAWN.get(section.kind, _unbuilt)(said, section, wide, y)
        y += 14
        if y > tall - 40:
            break
