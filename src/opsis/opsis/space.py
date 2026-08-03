"""The renderer — an emit-half flavour over the scene records.

One open :class:`~lexic.ir.IrTypeMap` from visual types to layout docs,
raising default: a scene citizen with no draw action is a drawn defect,
never silence. The table renders FROZEN scene; everything that moves —
pan, zoom, drags, window toggles — is the camera, which is the DOM.

Layer routing is the one structural decision here: :class:`Rail` records
draw in the wire ``<svg>``; every other citizen is a node in the world.
A new record type lands in the node layer without editing this split —
it still needs its own draw action, and raises until it has one.
"""

from __future__ import annotations

from typing import Sequence

from lexic.ir import IrAction, IrCat, IrDoc, IrLeaf, IrNone, IrSelf, IrTypeMap
from opsis.opsis.canvas import el, html, raw
from opsis.opsis.scene import Rail, Ring, Space, Window
from opsis.opsis.theme import css

__all__ = ["RENDER", "page", "render_scene"]


class DrawRing(IrLeaf[IrSelf, IrSelf]):
    """A ring: dot + label at its derived position; the payload stays IR."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        ring = Ring.ensure(n, "space: the ring action")
        return el(
            "div",
            {
                "class": f"nd ring {ring.hue}",
                "id": ring.name,
                "data-r": "14",
                "style": f"left:{ring.x}px;top:{ring.y}px",
            },
            el("div", {"class": "rdot"}),
            el("div", {"class": "rlabel"}, ring.name),
        )


class DrawRail(IrLeaf[IrSelf, IrSelf]):
    """A rail: a wire path by endpoint NAME — geometry is the camera's."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        rail = Rail.ensure(n, "space: the rail action")
        return el(
            "path",
            {
                "class": f"wire wire-{rail.hue}",
                "data-src": rail.src,
                "data-dst": rail.dst,
            },
        )


class DrawWindow(IrLeaf[IrSelf, IrSelf]):
    """A window: a bracket-cornered frame; its body shown as notation."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        win = Window.ensure(n, "space: the window action")
        body = "" if win.body is IrNone else repr(win.body)
        return el(
            "div",
            {
                "class": "frame",
                "data-frame": win.name,
                "style": (
                    f"left:{win.x}px;top:{win.y}px;width:{win.w}px;height:{win.h}px"
                ),
            },
            el(
                "header",
                None,
                el("span", None, win.name),
                el("b", {"class": "fx"}, "×"),
            ),
            el("div", {"class": "fbody"}, el("pre", {"class": "notation"}, body)),
        )


class DrawSpace(IrLeaf[IrSelf, IrSelf]):
    """A space: rails into the wire layer, every other citizen a node."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        space = Space.ensure(n, "space: the space action")
        wires = [_doc(d, kid) for kid in space if isinstance(kid, Rail)]
        nodes = [_doc(d, kid) for kid in space if not isinstance(kid, Rail)]
        svg = el("svg", {"id": "wires", "width": "1400", "height": "900"}, *wires)
        return IrCat(svg, *nodes)


def _doc(d: IrSelf, kid: IrSelf) -> IrDoc:
    """Dispatch one child and narrow the result to the doc tier."""
    return IrDoc.ensure(d.eval(d, kid, ()), "space: a drawn child")


RENDER: IrTypeMap = IrTypeMap(
    IrAction(Ring, DrawRing()),
    IrAction(Rail, DrawRail()),
    IrAction(Window, DrawWindow()),
    IrAction(Space, DrawSpace()),
)
"""The scene's emit half — one open table, raising default."""


def render_scene(scene: Space) -> str:
    """The scene fragment — wires + nodes, ready to sit inside ``#world``."""
    return html(_doc(RENDER, scene))


CAMERA = """
"use strict";
const space = document.getElementById("space");
const world = document.getElementById("world");
let scale = 0.9, tx = 30, ty = 20, panning = null, drag = null;
const apply = () =>
  world.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
apply();
const P = el => [parseFloat(el.style.left), parseFloat(el.style.top)];
function draw() {
  document.querySelectorAll("path[data-src]").forEach(p => {
    const s = document.getElementById(p.dataset.src);
    const d = document.getElementById(p.dataset.dst);
    if (!s || !d) return;
    const [x1, y1] = P(s), [x2, y2] = P(d);
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
    const r = 16;
    p.setAttribute("d", `M${x1 + dx / len * r},${y1 + dy / len * r} L` +
                        `${x2 - dx / len * r},${y2 - dy / len * r}`);
  });
}
draw();
space.addEventListener("wheel", e => {
  if (e.target.closest(".fbody")) return;
  e.preventDefault();
  const k = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  tx = e.clientX - (e.clientX - tx) * k;
  ty = e.clientY - (e.clientY - ty) * k;
  scale *= k; apply();
}, {passive: false});
space.addEventListener("pointerdown", e => {
  const header = e.target.closest(".frame header");
  const nd = e.target.closest(".nd");
  if (e.target.classList.contains("fx")) {
    e.target.closest(".frame").style.display = "none";
    return;
  }
  if (header) {
    const f = header.closest(".frame");
    const [x, y] = P(f);
    drag = {el: f, sx: e.clientX, sy: e.clientY, x, y};
  } else if (nd) {
    const [x, y] = P(nd);
    drag = {el: nd, sx: e.clientX, sy: e.clientY, x, y};
  } else if (!e.target.closest(".frame")) {
    panning = {x: e.clientX - tx, y: e.clientY - ty};
  }
});
window.addEventListener("pointermove", e => {
  if (panning) { tx = e.clientX - panning.x; ty = e.clientY - panning.y; apply(); return; }
  if (!drag) return;
  drag.el.style.left = (drag.x + (e.clientX - drag.sx) / scale) + "px";
  drag.el.style.top = (drag.y + (e.clientY - drag.sy) / scale) + "px";
  draw();
});
window.addEventListener("pointerup", () => { panning = null; drag = null; });
"""
"""The camera — DOM behavior only; the scene never moves."""


def page(scene: Space, title: str = "opsis", subtitle: str = "") -> str:
    """A complete standalone page for one scene — the display window.

    Deterministic by construction (no timestamps, no randomness): the
    same scene renders the same bytes, which is what makes a rendered
    page comparable across freeze and thaw.
    """
    doc = IrCat(
        raw("<!DOCTYPE html>"),
        el(
            "html",
            {"lang": "en"},
            el(
                "head",
                None,
                raw('<meta charset="utf-8">'),
                el("title", None, title),
                el("style", None, raw(css())),
            ),
            el(
                "body",
                None,
                el(
                    "div",
                    {"id": "hud"},
                    el("h1", None, title),
                    el("p", None, subtitle),
                ),
                el(
                    "div",
                    {"id": "space"},
                    el("div", {"id": "world"}, raw(render_scene(scene))),
                ),
                el("script", None, raw(CAMERA)),
            ),
        ),
    )
    return html(doc)
