"""Graphic — the railroad flavour: grammar IR emitted as SVG.

The same shape as a grammar flavour's emit half: an open
:class:`~lexic.ir.IrTypeMap` of per-node-type actions, each a custom
eval leaf (the ``IrEscape`` precedent — behavior as an IR citizen),
composed bottom-up. An action returns the node's LAYOUT as an
``IrTuple(w, h, mid, svg)`` — width, height, the entry/exit rail
height, and the SVG fragment drawn at the local origin. Altering one
node kind's look means replacing one action in the table; a new node
type is one more :class:`~lexic.ir.IrAction`, never an edit to a
cascade.

Topology is whole-graph, not per-node, so it renders as a plain layered
layout over :class:`opsis.eidolon.Topology` rather than a dispatch
table.
"""

from __future__ import annotations

from html import escape
from typing import Any, Sequence

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrCharClass,
    IrInt,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrStr,
    IrTuple,
    IrTypeMap,
)

from opsis_proto_0.eidolon import Topology

# ── the monospace metric (from the 260720 prototype) ──────────────────

CHAR_W = 7.3
BOX_H = 24
PAD_X = 9
GAP = 12
R = 8


def _tw(label: str) -> int:
    """Text advance width under the monospace metric."""
    return round(len(label) * CHAR_W)


def _rail(d: str) -> str:
    return f'<path class="rail" d="{d}"/>'


def _lay(node: IrSelf) -> tuple[int, int, int, str]:
    """Dispatch one grammar node through the table; unpack its layout."""
    got = RAIL_ACTIONS.resolve(node).eval(RAIL_ACTIONS, node, ())
    return int(got[0]), int(got[1]), int(got[2]), str(got[3])


def _pack(w: int, h: int, mid: int, svg: str) -> IrTuple:
    """A layout as the IR record the table's actions return."""
    return IrTuple(IrInt(w), IrInt(h), IrInt(mid), IrStr(svg))


def _box(cls: str, label: str, rx: int, extra: str = "") -> IrTuple:
    """A terminal-style box layout — the leaf actions share this body."""
    w = _tw(label) + 2 * PAD_X
    svg = (
        f"<g{extra}>"
        f'<rect class="{cls}" width="{w}" height="{BOX_H}" rx="{rx}"/>'
        f'<text class="{cls}" x="{w // 2}" y="{BOX_H // 2 + 4}" text-anchor="middle">'
        f"{escape(label)}</text></g>"
    )
    return _pack(w, BOX_H, BOX_H // 2, svg)


def _skip() -> IrTuple:
    """The empty arm — a plain rail with a dot."""
    w = 3 * GAP
    svg = _rail(f"M0,{BOX_H // 2} h{w}") + (
        f'<circle class="dot" cx="{w // 2}" cy="{BOX_H // 2}" r="2"/>'
    )
    return _pack(w, BOX_H, BOX_H // 2, svg)


# ── char-class spelling ───────────────────────────────────────────────

_NAMED = {9: "\\t", 10: "\\n", 13: "\\r", 32: "\\s"}


def class_spec(cc: Any) -> str:
    """A compact display spelling for a canonical (concrete) char class.

    Canonical classes carry no negation flag — ``[^a-z]`` arrives as a
    concrete interval set. The complement spelling is rendered too and
    the shorter of the two wins, so co-finite classes read as ``^…``.
    """
    plain = _spell(cc.intervals())
    comp = "^" + _spell(cc.complement().intervals())
    return plain if len(plain) <= len(comp) else comp


def _spell(intervals: Any) -> str:
    """Interval pairs to a class-body spelling (``a-z`` runs, escapes)."""
    out = []
    for lo, hi in intervals:
        out.append(_char(lo) if lo == hi else f"{_char(lo)}-{_char(hi)}")
    return "".join(out)


def _char(cp: int) -> str:
    """One codepoint's display spelling."""
    if cp in _NAMED:
        return _NAMED[cp]
    if 33 <= cp < 127:
        return chr(cp)
    return f"\\u{cp:04X}"


# ── the actions ───────────────────────────────────────────────────────


class _LayLiteral(IrLeaf[IrSelf, IrSelf]):
    """A literal — rounded box, quoted label."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        label = '"' + str(n).replace("\n", "\\n").replace("\t", "\\t") + '"'
        return _box("lit", label, rx=10)


class _LayClass(IrLeaf[IrSelf, IrSelf]):
    """A char class — angular box, interval spelling."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        return _box("cls", "[" + class_spec(n) + "]", rx=2)


class _LayAlphabet(IrLeaf[IrSelf, IrSelf]):
    """A token terminal — the tokenizer alphabet's spelling in a box."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        inner = n.inner
        if isinstance(inner, IrNot):
            label = f"!{inner[0]}"
        elif isinstance(inner, IrLiteral):
            label = str(inner)
        else:
            label = f"{n.encoding}:*"
        return _box("tok", label, rx=4)


class _LayRef(IrLeaf[IrSelf, IrSelf]):
    """A rule reference — navigable box."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        name = str(n)
        return _box("ref", name, rx=2, extra=f' class="ref" data-goto="{escape(name)}"')


class _LaySequence(IrLeaf[IrSelf, IrSelf]):
    """A sequence — items chained on one track."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        parts = [_lay(item) for item in n]
        if not parts:
            return _skip()
        above = max(p[2] for p in parts)
        below = max(p[1] - p[2] for p in parts)
        svg, x = "", 0
        for i, (w, _h, mid, frag) in enumerate(parts):
            if i:
                svg += _rail(f"M{x},{above} h{GAP}")
                x += GAP
            svg += f'<g transform="translate({x},{above - mid})">{frag}</g>'
            x += w
        return _pack(x, above + below, above, svg)


class _LayAlternation(IrLeaf[IrSelf, IrSelf]):
    """An alternation — stacked branch rails."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        arms = [_lay(arm) for arm in n]
        if len(arms) == 1:
            return _pack(*arms[0])
        inner = max(a[0] for a in arms)
        w = inner + 4 * R + 2 * GAP
        y, svg, mids = 0, "", []
        for aw, ah, amid, frag in arms:
            ax = 2 * R + GAP + (inner - aw) // 2
            svg += f'<g transform="translate({ax},{y})">{frag}</g>'
            svg += _rail(f"M{2 * R},{y + amid} h{ax - 2 * R}")
            svg += _rail(f"M{ax + aw},{y + amid} h{w - 2 * R - ax - aw}")
            mids.append(y + amid)
            y += ah + GAP
        mid = mids[0]
        for m in mids[1:]:
            svg += _rail(f"M0,{mid} q{R},0 {R},{R} V{m - R} q0,{R} {R},{R}")
            svg += _rail(f"M{w},{mid} q-{R},0 -{R},{R} V{m - R} q0,{R} -{R},{R}")
        svg += _rail(f"M0,{mid} h{2 * R}") + _rail(f"M{w - 2 * R},{mid} h{2 * R}")
        return _pack(w, y - GAP, mid, svg)


class _LayItem(IrLeaf[IrSelf, IrSelf]):
    """A quantified item — bypass and loop-back rails around the atom."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        iw, ih, imid, frag = _lay(n.atom)
        lo = int(n.quantifier.lo)
        hi = n.quantifier.hi
        hi = int(hi) if isinstance(hi, int) else None
        if lo == 1 and hi == 1:
            return _pack(iw, ih, imid, frag)
        w = iw + 4 * R + 2 * GAP
        ix = 2 * R + GAP
        mid = imid + (R + GAP if lo == 0 else 0)
        svg = f'<g transform="translate({ix},{mid - imid})">{frag}</g>'
        svg += _rail(f"M0,{mid} h{ix}") + _rail(f"M{ix + iw},{mid} h{GAP + 2 * R}")
        repeat = hi is None or hi > 1
        if repeat:
            yb = mid + (ih - imid) + GAP
            svg += _rail(
                f"M{ix + iw + GAP},{mid} q{R},0 {R},{R} V{yb - R} q0,{R} -{R},{R} "
                f"H{ix - R} q-{R},0 -{R},-{R} V{mid + R} q0,-{R} {R},-{R}"
            )
        if lo == 0:
            yt = mid - imid - GAP
            svg += _rail(
                f"M0,{mid} q{R},0 {R},-{R} V{yt + R} q0,-{R} {R},-{R} "
                f"H{w - 2 * R} q{R},0 {R},{R} V{mid - R} q0,{R} {R},{R}"
            )
        height = mid + (ih - imid) + (GAP + R if repeat else 0)
        label = ""
        if hi is not None and (hi > 1 or lo > 1):
            label = f"{{{lo},{hi}}}"
        elif lo > 1:
            label = f"{{{lo},}}"
        if label:
            svg += (
                f'<text class="quant" x="{w // 2}" y="{height + 10}" '
                f'text-anchor="middle">{label}</text>'
            )
            height += 12
        return _pack(w, height, mid, svg)


RAIL_ACTIONS: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, _LayLiteral()),
    IrAction(IrCharClass, _LayClass()),
    IrAction(IrAlphabet, _LayAlphabet()),
    IrAction(IrRuleRef, _LayRef()),
    IrAction(IrSequence, _LaySequence()),
    IrAction(IrAlternation, _LayAlternation()),
    IrAction(IrItem, _LayItem()),
)
"""The open per-node-type layout table — the railroad flavour's core."""


# ── documents ─────────────────────────────────────────────────────────


def railroad_html(ast: Any) -> str:
    """Every rule as a titled railroad section — one HTML fragment."""
    rules = list(ast.rules)
    start = str(rules[0].name) if rules else None
    out = []
    for rule in rules:
        name = str(rule.name)
        w, h, mid, frag = _lay(rule.body)
        tags = ' <span class="dim">(start)</span>' if name == start else ""
        tags += "" if rule.semantic else ' <span class="dim">structural</span>'
        out.append(
            f'<div class="rr-section" id="rr-{escape(name)}">'
            f"<h2>{escape(name)}{tags}</h2>"
            f'<svg class="rr" width="{w + 40}" height="{h + 16}">'
            f'<g transform="translate(20,8)">'
            + _rail(f"M-14,{mid} h14")
            + _rail(f"M{w},{mid} h14")
            + f'<circle class="dot" cx="-14" cy="{mid}" r="3"/>'
            + f'<circle class="dot" cx="{w + 14}" cy="{mid}" r="3"/>'
            + frag
            + "</g></svg></div>"
        )
    return "".join(out)


def topology_svg(topo: Topology) -> str:
    """The rule graph as layered columns — nodes navigable, edges curved."""
    columns: dict[int, list[str]] = {}
    for name in topo.names:
        level = topo.levels[name] if topo.levels[name] >= 0 else 99
        columns.setdefault(level, []).append(name)
    col_w, row_h = 190, 40
    pos: dict[str, tuple[int, int]] = {}
    width = height = 0
    for ci, level in enumerate(sorted(columns)):
        for ri, name in enumerate(columns[level]):
            pos[name] = (40 + ci * col_w, 30 + ri * row_h)
        height = max(height, 30 + len(columns[level]) * row_h)
        width = 40 + (ci + 1) * col_w
    out = []
    for src, dst in topo.edges:
        (x1, y1), (x2, y2) = pos[src], pos[dst]
        x1 += _tw(src) + 2 * PAD_X
        y1, y2 = y1 + BOX_H // 2, y2 + BOX_H // 2
        mx = (x1 + x2) // 2
        out.append(f'<path class="edge" d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}"/>')
    for name in topo.names:
        x, y = pos[name]
        w = _tw(name) + 2 * PAD_X
        cls = "node"
        cls += " start" if name == topo.start else ""
        cls += " cyclic" if name in topo.cyclic else ""
        cls += "" if topo.semantic[name] else " dim"
        out.append(
            f'<g class="{cls}" data-goto="{escape(name)}" transform="translate({x},{y})">'
            f'<rect width="{w}" height="{BOX_H}" rx="6"/>'
            f'<text x="{w // 2}" y="{BOX_H // 2 + 4}" text-anchor="middle">'
            f"{escape(name)}</text></g>"
        )
    return f'<svg width="{width + 60}" height="{height + 40}">{"".join(out)}</svg>'
