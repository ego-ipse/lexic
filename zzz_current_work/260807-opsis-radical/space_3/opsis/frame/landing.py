"""The file landing — a role-laned map of subjects and offered relations."""

from __future__ import annotations

from eidolon.value import graph as ir_graph
from opsis.frame.marks import ROW, Frame
from opsis.frame.places import draw as place_draw
from opsis.frame.tones import runs
from praxis.ingress import Ingress

from lexic.ir import IrSelf

__all__ = ["draw", "draw_value"]

PAD = 30.0
HEAD = 76.0
LANES = ("FILES", "READERS", "VALUES", "CAST / LOAD")


def _clip(words: str) -> str:
    """One wire-safe line from an engine answer."""
    return " ".join(words.split())


def _chip(
    said: Frame,
    x: float,
    y: float,
    room: float,
    label: str,
    tone: str,
    goes: str = "",
) -> float:
    """One measured map offer, optionally a door."""
    wide = min(room, max(54.0, runs("chip", label) + 16))
    said.box(x, y - 13, wide, 19, "field2")
    said.ring(x, y - 13, wide, 19, tone)
    said.text(x + 7, y + 1, tone, label, wide - 12, face="chip")
    if goes:
        said.hit(x, y - 13, wide, 19, "ingress", goes)
    return wide + 7


def draw(
    ingress: Ingress,
    wide: int,
    tall: int,
    *,
    history: bool = False,
    pending: str = "",
) -> Frame:
    """Draw every file subject, every retained answer, and every explicit edge."""
    ingress.poll()
    said = Frame(wide, tall)
    said.box(0, 0, wide, tall, "field")
    said.text(PAD, 34, "title", "THE MAP")
    said.text(PAD + 116, 34, "fsub", "subjects first · relations are offered")
    if history:
        said.text(wide - PAD, 34, "cool", "‹ back", anchor="r", face="chip")
        said.hit(wide - PAD - 68, 18, 72, 24, "ingress", "back")
    if pending:
        said.text(PAD, 58, "warm", f"PENDING · {pending}", wide - PAD * 2)
    said.line(0, HEAD - 10, wide, HEAD - 10, "hair")

    usable = wide - PAD * 2
    shares = (0.29, 0.23, 0.23, 0.25)
    starts = [PAD]
    for share in shares[:-1]:
        starts.append(starts[-1] + usable * share)
    widths = [usable * share for share in shares]
    for at, name in enumerate(LANES):
        said.text(starts[at], HEAD + 12, "hsub", name, face="hsub")
        if at:
            said.line(starts[at] - 12, HEAD - 2, starts[at] - 12, tall - 46, "hair")

    if not ingress.entries:
        y = HEAD + 54
        said.text(PAD, y, "ink", "No files were named. Enter through a corpus door:")
        y += ROW + 12
        for at, door in enumerate(ingress.doors):
            label = f"{door.name}/ · inspect its files"
            _chip(said, PAD, y, usable * 0.55, label, "cool", f"door:{at}")
            y += ROW + 8
    else:
        y = HEAD + 44
        visible = max(1, int((tall - y - 64) / 86))
        for at, entry in enumerate(ingress.entries[:visible]):
            top = y + at * 86
            said.line(PAD, top + 55, wide - PAD, top + 55, "hair")
            said.text(starts[0], top, "ink", entry.path.name, widths[0] - 18)
            if entry.pending:
                said.text(starts[0], top + ROW, "warm", "PENDING · asking pure readers")
                continue
            if entry.words:
                said.text(starts[0], top + ROW, "red", _clip(entry.words), widths[0] - 18)
                continue
            subject = entry.subject
            if subject is None:
                continue
            said.text(
                starts[0],
                top + ROW,
                "fsub",
                f"{subject.chars:,} chars · {subject.sid[:10]} · {entry.seconds * 1000:.1f} ms",
                widths[0] - 18,
            )
            reader_x, value_x, action_x = starts[1], starts[2], starts[3]
            for probe_at, answer in enumerate(subject.probes):
                if answer.reader.endswith(" grammar"):
                    tone = "green" if answer.accepted else "red"
                    reader_x += _chip(
                        said,
                        reader_x,
                        top,
                        starts[2] - reader_x - 16,
                        answer.reader.removesuffix(" grammar"),
                        tone,
                    )
                    if answer.accepted:
                        flavour = answer.reader.split()[0].casefold()
                        for doc_at, other in enumerate(ingress.entries):
                            if doc_at == at or other.subject is None:
                                continue
                            label = f"read {other.path.name} · {flavour.upper()}"
                            action_x += _chip(
                                said,
                                action_x,
                                top,
                                wide - PAD - action_x,
                                label,
                                "cool",
                                f"read:{at}:{doc_at}:{flavour}",
                            )
                            break
                elif answer.accepted and isinstance(answer.value, IrSelf):
                    value_x += _chip(
                        said,
                        value_x,
                        top,
                        starts[3] - value_x - 16,
                        answer.reader,
                        "violet",
                        f"value:{at}:{probe_at}",
                    )
                elif answer.reader != "Python payload" and answer.words:
                    said.text(
                        starts[1],
                        top + ROW,
                        "red",
                        f"{answer.reader} — {_clip(answer.words)}",
                        widths[1] - 18,
                        face="fsub",
                    )
            payload_offer = next(
                (answer for answer in subject.probes if answer.reader == "Python payload"),
                None,
            )
            if entry.payload_pending:
                said.text(starts[3], top + ROW, "warm", "PENDING · running payload")
            elif entry.payload is not None:
                if entry.payload.accepted:
                    loaded = entry.payload.value
                    for name in getattr(loaded, "exports", ()):
                        _chip(
                            said,
                            starts[3],
                            top + ROW,
                            widths[3] - 18,
                            f"open {name}",
                            "green",
                            f"payloadvalue:{at}:{name}",
                        )
                        break
                else:
                    said.text(
                        starts[3], top + ROW, "red", _clip(entry.payload.words), widths[3] - 18
                    )
            elif payload_offer is not None:
                _chip(
                    said,
                    starts[3],
                    top + ROW,
                    widths[3] - 18,
                    "RUN PYTHON · explicit",
                    "warm",
                    f"payload:{at}",
                )
        if len(ingress.entries) > visible:
            said.text(
                PAD,
                tall - 54,
                "fsub",
                f"{len(ingress.entries) - visible} more subjects · derive less, never clip",
            )

    said.line(0, tall - 38, wide, tall - 38, "hair")
    said.text(PAD, tall - 15, "fsub", "THE INSTRUMENT · map is a landing, not a room")
    return said


def draw_value(
    value: IrSelf,
    name: str,
    reader: str,
    wide: int,
    tall: int,
) -> Frame:
    """One file result in the existing generic value-room surface."""
    walk = ir_graph(value)
    room = "\n".join(
        [
            f"#PLACE file:value value {name} · read by {reader}",
            "#SEC title 1",
            f"{type(value).__name__} — a live Lexic value",
            "#SEC kv 3",
            f"reader\t{reader}",
            f"unique nodes\t{len(walk.nodes)}",
            f"edges\t{len(walk.edges)}",
            "#SEC irvalue 1",
            "value",
            "",
        ]
    )
    said = Frame(wide, tall)
    place_draw(said, room, wide, tall, value)
    said.hit(wide - PAD - 70, 20, 74, 26, "ingress", "back")
    return said
