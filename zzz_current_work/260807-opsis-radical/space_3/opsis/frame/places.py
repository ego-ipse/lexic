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

from eidolon.topology import reachable
from eidolon.value import wire
from opsis.frame.marks import ROW, Frame
from opsis.frame.tones import runs

from lexic.ir import IrAst
from lexic.ir.spine.spine import IrSelf

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


def _title(
    said: Frame,
    section: Section,
    _wide: int,
    y: float,
    _value: IrSelf | None,
    _ast: IrAst | None,
) -> float:
    for line in section.lines:
        said.text(PAD, y, "ink", line)
        y += ROW + 4
    return y


def _kv(
    said: Frame,
    section: Section,
    wide: int,
    y: float,
    _value: IrSelf | None,
    _ast: IrAst | None,
) -> float:
    """Facts as pairs — the name on the left, what it is on the right."""
    keys = [line.split("\t")[0] for line in section.lines]
    step = max((runs("fsub", key) for key in keys), default=0.0) + 24
    for line in section.lines:
        key, _, value = line.partition("\t")
        said.text(PAD, y, "fsub", key)
        said.text(PAD + step, y, "ink", value, wide - PAD * 2 - step)
        y += ROW
    return y


def _list(
    said: Frame,
    section: Section,
    wide: int,
    y: float,
    _value: IrSelf | None,
    _ast: IrAst | None,
) -> float:
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


def _refusal(
    said: Frame,
    section: Section,
    wide: int,
    y: float,
    _value: IrSelf | None,
    _ast: IrAst | None,
) -> float:
    """A room nobody authored says so, in place — in the words it has."""
    for line in section.lines:
        said.text(PAD, y, "red", line, wide - PAD * 2)
        y += ROW
    return y


def _unbuilt(
    said: Frame,
    section: Section,
    _wide: int,
    y: float,
    _value: IrSelf | None,
    _ast: IrAst | None,
) -> float:
    """A section this frame draws no shape for — named, never silently dropped.

    The raising default, said on screen: an unauthored kind draws its own
    name, so coverage is visible rather than blank.
    """
    said.text(PAD, y, "dimmer", f"[{section.kind}] — this frame draws no shape for it")
    return y + ROW


def _irvalue(
    said: Frame,
    section: Section,
    wide: int,
    y: float,
    value: IrSelf | None,
    _ast: IrAst | None,
) -> float:
    """A VALUE as the value it is — what it HOLDS, one row per child.

    Not a tree dump, and not the facts again: the room's own section already
    counted the nodes. This is the value's own children — the field that
    names each one, what it is, and its payload where it has one. Tier is the
    colour, because the tier is what the thing IS.
    """
    if not section.lines or value is None:
        return _unbuilt(said, section, wide, y, value, _ast)
    kids: list[str] = []
    lines = wire(value).split("\n")
    for at, line in enumerate(lines):
        if line.startswith("#KIDS"):
            count = int(line.split(" ")[1])
            kids = lines[at + 1 : at + 1 + count]
            break
    if not kids:
        said.text(PAD, y, "fsub", "this value holds nothing — it IS its payload")
        return y + ROW
    for line in kids[:26]:
        parts = line.split(" ")
        if len(parts) < 5:
            continue
        _i, label, kind, tier_of, count = parts[:5]
        payload = " ".join(parts[5:])
        said.line(PAD, y - 13, PAD, y + 5, TIERS.get(tier_of, "dimmer"))
        said.text(PAD + 12, y, "violet", label, 150)
        said.text(PAD + 172, y, "ink", kind, 210)
        said.text(
            PAD + 392,
            y,
            "green" if payload else "fsub",
            payload or f"{count} children",
            wide - PAD - 402,
        )
        y += ROW + 2
    if len(kids) > 26:
        said.text(PAD + 12, y, "dimmer", f"{len(kids) - 26} more")
        y += ROW
    return y


# .irrow.t-record / .t-tuple / .t-scalar / .t-absence / .t-map
TIERS = {
    "record": "violet",
    "tuple": "cool",
    "scalar": "green",
    "absence": "dimmer",
    "map": "warm",
}


def _graphview(
    said: Frame,
    section: Section,
    wide: int,
    y: float,
    _value: IrSelf | None,
    ast: IrAst | None,
) -> float:
    """A rule's own NEIGHBOURHOOD — what it reaches, and how far.

    A rule's neighbourhood is a different graph from the whole grammar's, and
    answering a question about one rule with a picture of everything is the
    thing `reachable` exists to avoid. Columns are distance: the rule itself,
    then what it reaches in one step, then two.
    """
    name = section.lines[0] if section.lines else ""
    name = name.removeprefix("rule:")
    if ast is None or not name:
        return _unbuilt(said, section, wide, y, _value, ast)
    kept, depth = reachable(ast, name)
    if len(depth) <= 1:
        said.text(
            PAD, y, "fsub", f"{name} reaches nothing — it is a leaf of the grammar"
        )
        return y + ROW
    bands: dict[int, list[str]] = {}
    for rule, at in sorted(depth.items(), key=lambda kv: (kv[1], kv[0])):
        bands.setdefault(at, []).append(rule)
    step = min(260.0, (wide - PAD * 2) / max(1, len(bands)))
    tall = ROW + 6
    at_of: dict[str, tuple[float, float]] = {}
    for band, rules in sorted(bands.items()):
        for row, rule in enumerate(rules[:14]):
            at_of[rule] = (PAD + band * step, y + row * tall)
    for a, b in kept:
        one, two = at_of.get(a), at_of.get(b)
        if one is None or two is None or one == two:
            continue
        said.line(one[0] + 120, one[1] + 6, two[0], two[1] + 6, "cool_wash")
    for rule, (rx, ry) in at_of.items():
        here = rule == name
        room = min(118.0, runs("chip", rule) + 14)
        said.box(rx, ry - 4, room, 16, "field2")
        said.text(
            rx + 6, ry + 8, "warm" if here else "ink", rule, room - 10, face="chip"
        )
        if not here:
            said.hit(rx, ry - 4, room, 16, "place", f"rule:{rule}")
    deepest = max(len(rules) for rules in bands.values())
    return y + min(deepest, 14) * tall + 8


DRAWN = {
    "title": _title,
    "kv": _kv,
    "list": _list,
    "refusal": _refusal,
    "irvalue": _irvalue,
    "graphview": _graphview,
}


def draw(
    said: Frame,
    said_wire: str,
    wide: int,
    tall: int,
    value: IrSelf | None = None,
    ast: IrAst | None = None,
) -> None:
    """The room, whole — its name, its facts, and the doors it opens onto.

    :param value: what this room is ABOUT, when it is about a value — handed
        to every section rather than reached for, so a section that needs it
        says so in its own signature.
    :param ast: the grammar the room's subject lives in, for the sections that
        draw a neighbourhood rather than a value.
    """
    pid, kind, says, sections = read(said_wire)
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
        y = DRAWN.get(section.kind, _unbuilt)(said, section, wide, y, value, ast)
        y += 14
        if y > tall - 40:
            break
