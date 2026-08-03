"""Railroad diagrams — a rule as the track its text must walk.

Two open tables walk the grammar: :data:`MEASURE` sizes every construct
bottom-up, :data:`EMIT` draws it at a position carried on the ``nc``
channel. Both raise on a construct they do not know, and the drawing
boundary turns that into a drawn refusal — a diagram is never silently
partial.

References carry ``data-rule``, so a railroad points like everything
else does, and clicking one opens that rule's own diagram.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrCharClass,
    IrChr,
    IrInt,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrStr,
    IrTuple,
    IrTypeMap,
)

__all__ = ["EMIT", "MEASURE", "RAIL_CSS", "rule_svg"]

BOX = 26
CHAR = 7.2
PAD = 18
GAP = 26
VGAP = 14
LOOP = 16


def _glyph(point: int) -> str:
    """One code point, spelled so it can be read."""
    named = {9: "\\t", 10: "\\n", 13: "\\r", 32: "␣"}
    if point in named:
        return named[point]
    return chr(point) if 33 <= point < 127 else f"\\x{point:02x}"


def _encoding(atom: IrSelf, x: int, y: int, w: int) -> str:
    """The badge an atom wears when it is read under a named encoding.

    Ordinals mean nothing until something says what alphabet they are
    in, so an atom scoped to an encoding says which — and one that is
    not scoped wears nothing, because ``unicode`` is not a decision
    anybody made.
    """
    if not isinstance(atom, IrAlphabet):
        return ""
    name = escape(str(atom.encoding))
    return (
        f'<text class="rr-enc" x="{x + w - 3}" y="{y - 3}" '
        f'text-anchor="end">{name}</text>'
    )


def _label(atom: IrSelf) -> str:
    """What a leaf atom says on its box."""
    if isinstance(atom, IrLiteral):
        body = str(atom)
        return f'"{body[:20]}…"' if len(body) > 20 else f'"{body}"'
    if isinstance(atom, IrRuleRef):
        return str(atom)
    if isinstance(atom, IrCharClass):
        parts: list[str] = []
        for member in atom:
            if isinstance(member, IrRange):
                parts.append(f"{_glyph(int(member.lo))}–{_glyph(int(member.hi))}")
            elif isinstance(member, IrChr):
                parts.append(_glyph(int(member)))
        body = "".join(parts)
        return f"[{body[:20]}…]" if len(body) > 20 else f"[{body}]"
    if isinstance(atom, IrAlphabet):
        return f"⟨{atom.encoding}⟩ {_label(atom.inner)}"
    return type(atom).__name__


def _size(w: int, h: int, mid: int) -> IrTuple:
    """A measurement: width, height, where the track enters."""
    return IrTuple(IrInt(w), IrInt(h), IrInt(mid))


def _m(node: IrSelf) -> tuple[int, int, int]:
    """Measure ``node`` through the table."""
    got = tuple(IrTuple.ensure(MEASURE.eval(MEASURE, node, ()), "graphic: a size"))
    return (
        int(IrInt.ensure(got[0], "graphic: w")),
        int(IrInt.ensure(got[1], "graphic: h")),
        int(IrInt.ensure(got[2], "graphic: mid")),
    )


class _MLeaf(IrLeaf[IrSelf, IrSelf]):
    """A leaf atom is one box around its label."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        return _size(int(2 * PAD + CHAR * len(_label(n))), BOX, BOX // 2)


class _MSeq(IrLeaf[IrSelf, IrSelf]):
    """A sequence lays its items along one line."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        seq = IrSequence.ensure(n, "graphic: measure a sequence")
        kids = [_m(kid) for kid in seq]
        if not kids:
            return _size(2 * PAD, BOX, BOX // 2)
        mid = max(k[2] for k in kids)
        drop = max(k[1] - k[2] for k in kids)
        return _size(sum(k[0] for k in kids) + GAP * (len(kids) - 1), mid + drop, mid)


class _MAlt(IrLeaf[IrSelf, IrSelf]):
    """An alternation stacks its arms and rails around them."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        alt = IrAlternation.ensure(n, "graphic: measure an alternation")
        kids = [_m(arm) for arm in alt]
        if not kids:
            return _size(2 * PAD, BOX, BOX // 2)
        if len(kids) == 1:
            return _size(*kids[0])
        return _size(
            max(k[0] for k in kids) + 2 * GAP,
            sum(k[1] for k in kids) + VGAP * (len(kids) - 1),
            kids[0][2],
        )


class _MItem(IrLeaf[IrSelf, IrSelf]):
    """An item is its atom plus whatever loop its quantifier earns."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        item = IrItem.ensure(n, "graphic: measure an item")
        w, h, mid = _m(item.atom)
        lo, hi = int(item.quantifier.lo), item.quantifier.hi
        many = not isinstance(hi, int) or int(hi) > 1
        skip = lo == 0
        pad = LOOP if (many or skip) else 0
        return _size(
            w + 2 * pad,
            h + (LOOP if many else 0) + (LOOP if skip else 0),
            mid + (LOOP if many else 0),
        )


MEASURE: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, _MLeaf()),
    IrAction(IrRuleRef, _MLeaf()),
    IrAction(IrCharClass, _MLeaf()),
    IrAction(IrAlphabet, _MLeaf()),
    IrAction(IrSequence, _MSeq()),
    IrAction(IrAlternation, _MAlt()),
    IrAction(IrItem, _MItem()),
)
"""The measuring half — one open table, raising default."""


def _track(x1: int, y1: int, x2: int, y2: int) -> str:
    """A straight run of track."""
    return f'<path class="rr-line" d="M{x1},{y1} L{x2},{y2}"/>'


def _at(nc: Sequence[IrSelf]) -> tuple[int, int]:
    """The position this draw is happening at."""
    parts = tuple(IrTuple.ensure(nc[0], "graphic: a position"))
    return (
        int(IrInt.ensure(parts[0], "graphic: x")),
        int(IrInt.ensure(parts[1], "graphic: y")),
    )


def _draw(node: IrSelf, x: int, y: int) -> str:
    """Draw ``node`` at ``(x, y)`` and hand back its markup."""
    got = EMIT.eval(EMIT, node, (IrTuple(IrInt(x), IrInt(y)),))
    return str(IrStr.ensure(got, "graphic: drawn track"))


class _ELeaf(IrLeaf[IrSelf, IrSelf]):
    """A leaf atom: a box, rounded for a literal, square for a class."""

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        x, y = _at(nc)
        w, h, _mid = _m(n)
        kind = (
            "rr-ref"
            if isinstance(n, IrRuleRef)
            else ("rr-lit" if isinstance(n, IrLiteral) else "rr-cls")
        )
        points = (
            f' data-rule="{escape(str(n), quote=True)}" data-open="rr-{escape(str(n), quote=True)}"'
            if isinstance(n, IrRuleRef)
            else ""
        )
        radius = 13 if kind == "rr-lit" else 3
        return IrStr(
            f'<g class="{kind}"{points}>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}"/>'
            f'<text x="{x + w // 2}" y="{y + h // 2 + 4}">{escape(_label(n))}</text>'
            f"{_encoding(n, x, y, w)}"
            f"</g>"
        )


class _ESeq(IrLeaf[IrSelf, IrSelf]):
    """A sequence: its items joined along the entry line."""

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        seq = IrSequence.ensure(n, "graphic: draw a sequence")
        x, y = _at(nc)
        _w, _h, mid = _m(seq)
        if not seq:
            return IrStr(
                f'<text class="rr-eps" x="{x + PAD}" y="{y + mid + 4}">ε</text>'
            )
        return IrStr("".join(_chain(seq, x, y + mid)))


def _chain(seq: Sequence[IrSelf], x: int, line: int) -> list[str]:
    """Each part in turn, joined left to right by a track."""
    out: list[str] = []
    cursor = x
    for i, kid in enumerate(seq):
        width, _height, mid = _m(kid)
        if i:
            out.append(_track(cursor, line, cursor + GAP, line))
            cursor += GAP
        out.append(_draw(kid, cursor, line - mid))
        cursor += width
    return out


class _EAlt(IrLeaf[IrSelf, IrSelf]):
    """An alternation: one rail out to each arm and back to one exit."""

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        alt = IrAlternation.ensure(n, "graphic: draw an alternation")
        x, y = _at(nc)
        w, _h, mid = _m(alt)
        arms = list(alt)
        if len(arms) == 1:
            return IrStr(_draw(arms[0], x, y))
        out: list[str] = []
        top = y
        for arm in arms:
            out.extend(_arm(arm, x, top, (w, y + mid)))
            top += _m(arm)[1] + VGAP
        return IrStr("".join(out))


def _arm(arm: IrSelf, x: int, top: int, span: tuple[int, int]) -> list[str]:
    """One arm: a rail out to it, the arm, a rail back to the exit."""
    width, spine = span
    aw, _ah, amid = _m(arm)
    line = top + amid
    return [
        f'<path class="rr-line" d="M{x},{spine} '
        f'C{x + GAP // 2},{spine} {x + GAP // 2},{line} {x + GAP},{line}"/>',
        _draw(arm, x + GAP, top),
        f'<path class="rr-line" d="M{x + GAP + aw},{line} '
        f"C{x + width - GAP // 2},{line} {x + width - GAP // 2},{spine} "
        f'{x + width},{spine}"/>',
    ]


class _EItem(IrLeaf[IrSelf, IrSelf]):
    """An item: its atom, a loop back over it, a skip under it."""

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        item = IrItem.ensure(n, "graphic: draw an item")
        many, skip = _repeats(item)
        return IrStr("".join(_item_parts(item, _at(nc), (many, skip))))


def _repeats(item: IrItem) -> tuple[bool, bool]:
    """Whether an item may repeat, and whether it may be absent."""
    hi = item.quantifier.hi
    return not isinstance(hi, int) or int(hi) > 1, int(item.quantifier.lo) == 0


def _item_parts(
    item: IrItem, at: tuple[int, int], rails: tuple[bool, bool]
) -> list[str]:
    """The atom, and whichever of the two rails this item wears."""
    x, y = at
    many, skip = rails
    width, _height, mid = _m(item)
    aw, ah, amid = _m(item.atom)
    pad = LOOP if (many or skip) else 0
    out: list[str] = []
    if pad:
        out.append(_track(x, y + mid, x + pad, y + mid))
        out.append(_track(x + pad + aw, y + mid, x + width, y + mid))
    out.append(_draw(item.atom, x + pad, y + mid - amid))
    if many:
        out.append(_loop((x, y + 3), y + mid, (width, pad, aw)))
    if skip:
        out.append(_skip(x, y + mid, width, y + mid + (ah - amid) + LOOP - 3))
    return out


def _loop(at: tuple[int, int], spine: int, box: tuple[int, int, int]) -> str:
    """The rail over an atom that may repeat — out the right, back the left."""
    x, top = at
    width, pad, inner = box
    return (
        f'<path class="rr-loop" d="M{x + pad + inner},{spine} '
        f"C{x + width},{spine} {x + width},{top} {x + width - LOOP // 2},{top} "
        f"L{x + LOOP // 2},{top} "
        f'C{x},{top} {x},{spine} {x + pad},{spine}"/>'
    )


def _skip(x: int, spine: int, width: int, under: int) -> str:
    """The rail under an atom that may be absent."""
    return (
        f'<path class="rr-skip" d="M{x},{spine} '
        f"C{x + LOOP // 2},{spine} {x + LOOP // 2},{under} "
        f"{x + LOOP},{under} L{x + width - LOOP},{under} "
        f'C{x + width},{under} {x + width},{spine} {x + width},{spine}"/>'
    )


EMIT: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, _ELeaf()),
    IrAction(IrRuleRef, _ELeaf()),
    IrAction(IrCharClass, _ELeaf()),
    IrAction(IrAlphabet, _ELeaf()),
    IrAction(IrSequence, _ESeq()),
    IrAction(IrAlternation, _EAlt()),
    IrAction(IrItem, _EItem()),
)
"""The drawing half — one open table, raising default."""

RAIL_CSS = """
.rr { overflow:auto; padding:4px 0 2px; }
.rr .rr-enc { fill:var(--magenta); font-size:8px; letter-spacing:.8px; }
.rr svg { display:block; }
.rr .rr-line, .rr .rr-loop, .rr .rr-skip { fill:none; stroke:var(--dim);
  stroke-width:1.1; }
.rr .rr-loop { stroke:var(--cyandim); }
.rr .rr-skip { stroke:var(--cyandim); stroke-dasharray:3 4; }
.rr rect { fill:rgba(8,16,28,.92); stroke-width:1.1; }
.rr text { font:10.5px "Cascadia Mono", monospace; text-anchor:middle;
  fill:var(--text); }
.rr .rr-lit rect { stroke:var(--green); }
.rr .rr-ref rect { stroke:var(--cyan); cursor:pointer; }
.rr .rr-cls rect { stroke:var(--amber); }
.rr .rr-eps { fill:var(--dim); text-anchor:start; }
.rr .stop { fill:none; stroke:var(--dim); stroke-width:1.1; }
"""
"""The railroad's own style, scoped under ``.rr``."""


def rule_svg(rule: IrRule) -> str:
    """One rule's railroad: entry track, its body, exit track."""
    w, h, mid = _m(rule.body)
    body = _draw(rule.body, 22, 10)
    y = 10 + mid
    return (
        f'<svg width="{w + 46}" height="{h + 20}">'
        f'<path class="stop" d="M4,{y - 6} L4,{y + 6} M4,{y} L22,{y}"/>'
        f"{body}"
        f'<path class="stop" d="M{w + 22},{y} L{w + 38},{y} '
        f'M{w + 38},{y - 6} L{w + 38},{y + 6} M{w + 42},{y - 6} L{w + 42},{y + 6}"/>'
        f"</svg>"
    )
