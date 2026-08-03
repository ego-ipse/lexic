"""The renderer and the camera — the scene drawn, and everything that moves.

Drawing is an emit-half flavour: one open table from visual types to
layout docs, raising default, so a citizen with no draw action is a
drawn defect rather than silence.

Two rules hold it together. **Layer routing**: rails draw into the wire
``<svg>``, everything else is a node in the world, and a moon draws
INSIDE its ring — which is what makes it orbit for free. **Chrome is
intrinsic**: :func:`frame` is the only way a window exists and it always
drags, minimizes, maximizes, closes and resizes, so an unreachable
window is not expressible.

The camera owns everything that moves and the scene owns nothing that
does. It also snapshots and restores itself, which is what lets the
server replace the world under it without disturbing a thing.
"""

from __future__ import annotations

import math
from typing import NamedTuple, Sequence

from lexic.ir import IrAction, IrCat, IrDoc, IrLeaf, IrNone, IrSelf, IrTypeMap
from opsis.opsis.draw.canvas import el, html, raw
from opsis.opsis.draw.scene import Moon, Rail, Ring, Space
from opsis.opsis.draw.theme import css

__all__ = [
    "CAMERA",
    "RENDER",
    "RING_R",
    "Box",
    "Frame",
    "frame",
    "page",
    "render_scene",
]

RING_R = 34
ORBIT_R = 96
ORBIT_ARC = 118

ACTS = {
    "reading": (
        ("unplug", "⊗", "unplug — nothing reads it, but it is kept"),
        ("remove", "×", "remove it from the session"),
        ("fold", "⌖", "fold what is above it into a capsule"),
    ),
}
"""What a node lets you do to it. Unplugging is not removing."""


def _lozenge(ring: Ring) -> tuple[IrDoc, ...]:
    """The ◈ a ring wears when it is ABOUT something.

    A ring's payload is the lexic node it stands for, carried whole. The
    lozenge is how you reach it — and because the payload rides in the
    scene record, editing the scene edits what the lozenge opens.
    """
    if ring.payload is IrNone:
        return ()
    return (
        el(
            "b",
            {
                "class": "act ir",
                "title": f"what it is about — {type(ring.payload).__name__}",
                "data-open": f"ir-{ring.name}",
            },
            "◈",
        ),
    )


class Box(NamedTuple):
    """Where a window sits and how big it is, in world pixels."""

    x: int = 0
    y: int = 0
    w: int = 420
    h: int = 300


class Frame(NamedTuple):
    """Everything about a window except what is inside it.

    :ivar ident: What a gesture toggles it by.
    :ivar owner: The node it belongs to, so the camera can tether it.
    :ivar sub: Opened inside another window, and stays inside it.
    :ivar hud: Belongs to the viewport rather than the panned world.
    """

    ident: str
    title: str
    box: Box = Box()
    shown: bool = True
    editor: bool = False
    sub: bool = False
    hud: bool = False
    owner: str = ""
    rule: str = ""


def frame(spec: Frame, *body: IrDoc) -> IrDoc:
    """One window — the ONLY way a window exists."""
    classes = " ".join(
        ["frame"] + ["editor"] * spec.editor + ["sub"] * spec.sub + ["hud"] * spec.hud
    )
    size = f"width:{spec.box.w}px;height:{spec.box.h}px"
    place = size if spec.hud else f"left:{spec.box.x}px;top:{spec.box.y}px;{size}"
    attrs: dict[str, str | None] = {
        "class": classes,
        "data-frame": spec.ident,
        "style": place + ("" if spec.shown else ";display:none"),
    }
    if spec.owner:
        attrs["data-owner"] = spec.owner
    head: dict[str, str | None] | None = {"data-rule": spec.rule} if spec.rule else None
    return el(
        "div",
        attrs,
        el(
            "header",
            None,
            el("span", head, spec.title),
            el("b", {"class": "min", "title": "minimize"}, "–"),
            el("b", {"class": "max", "title": "maximize"}, "□"),
            el("b", {"class": "close", "title": "close"}, "×"),
        ),
        el("div", {"class": "body"}, *body),
        *_edges(),
    )


_SIDES = ("n", "s", "e", "w", "ne", "nw", "se", "sw")
"""Every side and corner a window can be taken by."""


def _edges() -> tuple[IrDoc, ...]:
    """The eight grips a window resizes from.

    All eight, because a window whose only handle is its bottom-right
    corner has to be moved before it can be made bigger upward, and
    that is two gestures for one intention.
    """
    return tuple(
        el("div", {"class": f"grip g-{side}", "data-side": side}) for side in _SIDES
    )


SUB_R = 86
"""How far a group's own moons ride from it — closer than the main orbit."""


def orbit(index: int, count: int, radius: int = 0) -> tuple[int, int]:
    """Where the ``index``-th of ``count`` moons rides, from the core.

    Constant offsets on a fixed radius: a moon keeps its distance
    however the ring is dragged, because it has no position of its own
    to lose.
    """
    reach = radius or ORBIT_R
    if count <= 1:
        return reach, 0
    step = ORBIT_ARC / (count - 1)
    angle = math.radians(-ORBIT_ARC / 2 + step * index)
    return round(reach * math.cos(angle)), round(reach * math.sin(angle))


class DrawRing(IrLeaf[IrSelf, IrSelf]):
    """A ring: a breathing disc, a core, its title, its acts, its moons."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        ring = Ring.ensure(n, "space: the ring action")
        kind, _, value = ring.tag.partition(":")
        attrs: dict[str, str | None] = {
            "class": f"nd ring {ring.hue} {ring.state}".strip(),
            "id": ring.name,
            "data-r": str(RING_R),
            "style": f"left:{ring.x}px;top:{ring.y}px",
        }
        if kind:
            attrs[f"data-{kind}"] = value
        moons = tuple(ring.moons)
        return el(
            "div",
            attrs,
            el("div", {"class": "disc"}),
            el("div", {"class": "core"}),
            el(
                "div",
                {"class": "title"},
                ring.label or ring.name,
                el("span", None, ring.sub),
            ),
            *(
                el("b", {"class": f"act {act}", "title": why}, glyph)
                for act, glyph, why in ACTS.get(kind, ())
            ),
            *_lozenge(ring),
            *(
                _moon(Moon.ensure(m, "space: a moon"), i, len(moons))
                for i, m in enumerate(moons)
            ),
        )


def _moon(moon: Moon, index: int, count: int) -> IrDoc:
    """One moon in its ring's orbit — a reading, one click from open.

    A moon carrying moons is a GROUP: it opens its own orbit in place
    rather than a window, so a node with twenty readings wears seven
    and the rest are one click away instead of all at once.
    """
    x, y = orbit(index, count)
    inner = tuple(moon.moons)
    attrs: dict[str, str | None] = {
        "class": "moon group" if inner else "moon",
        "id": moon.name,
        "style": f"left:{x}px;top:{y}px",
    }
    if inner:
        attrs["data-orbit"] = moon.name
    else:
        attrs["data-open"] = f"w-{moon.name}"
    body: list[IrDoc] = [
        el("div", {"class": "dot"}),
        el("em", None, moon.label or moon.kind),
    ]
    if inner:
        body.append(
            el(
                "div",
                {"class": "sub"},
                *(
                    _sub_moon(Moon.ensure(m, "space: a sub-moon"), i, len(inner))
                    for i, m in enumerate(inner)
                ),
            )
        )
    return el("div", attrs, *body)


def _sub_moon(moon: Moon, index: int, count: int) -> IrDoc:
    """One reading inside a group's own orbit."""
    x, y = orbit(index, count, SUB_R)
    return el(
        "div",
        {
            "class": "moon inner",
            "id": moon.name,
            "data-open": f"w-{moon.name}",
            "style": f"left:{x}px;top:{y}px",
        },
        el("div", {"class": "dot"}),
        el("em", None, moon.label or moon.kind),
    )


class DrawRail(IrLeaf[IrSelf, IrSelf]):
    """A reading: a bowed wire in two layers, carrying what it claims."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        rail = Rail.ensure(n, "space: the rail action")
        wire: dict[str, str | None] = {
            "data-src": rail.src,
            "data-dst": rail.dst,
            "data-bow": str(rail.bow),
        }
        under = el("path", {"class": f"rail rail-{rail.hue} under", **wire})
        over = el("path", {"class": f"rail rail-{rail.hue} over", **wire})
        if not rail.label:
            return IrCat(under, over)
        return IrCat(
            under,
            over,
            el(
                "text",
                {"class": f"raillabel rl-{rail.hue}", **wire},
                el("tspan", {"class": "big"}, f"{rail.label} ▾"),
                el("tspan", {"class": "small", "dy": "12"}, rail.sub),
            ),
        )


class DrawSpace(IrLeaf[IrSelf, IrSelf]):
    """A space: rails into the wire layer, every other citizen a node."""

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        space = Space.ensure(n, "space: the space action")
        wires = [_doc(d, k) for k in space if isinstance(k, Rail)]
        nodes = [_doc(d, k) for k in space if not isinstance(k, Rail)]
        return IrCat(
            el("svg", {"id": "wires", "width": "9000", "height": "6000"}, *wires),
            *nodes,
        )


def _doc(d: IrSelf, kid: IrSelf) -> IrDoc:
    """Dispatch one child and narrow the result to the doc tier."""
    return IrDoc.ensure(d.eval(d, kid, ()), "space: a drawn child")


RENDER: IrTypeMap = IrTypeMap(
    IrAction(Ring, DrawRing()),
    IrAction(Rail, DrawRail()),
    IrAction(Space, DrawSpace()),
)
"""The scene's emit half — one open table, raising default."""


def render_scene(scene: Space) -> str:
    """The scene fragment — wires and nodes, ready to sit in ``#world``.

    Wrapped in one element so it can be replaced on its own. Positioned
    at the origin and sized to nothing, so it is the containing block
    its absolutely-placed children already resolved against — swapping
    it moves nothing.
    """
    return html(el("div", {"id": "nodes"}, _doc(RENDER, scene)))


CAMERA = r"""
"use strict";
const space = document.getElementById("space");
const world = document.getElementById("world");
let scale = .85, tx = 60, ty = 40, panning = null, drag = null, zTop = 20;
const folds = new Set();
const apply = () =>
  world.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
const P = el => [parseFloat(el.style.left) || 0, parseFloat(el.style.top) || 0];
const live = el => el && el.offsetParent !== null;

function ends(a, b, bow) {
  const [x1, y1] = P(a), [x2, y2] = P(b);
  const r1 = +a.dataset.r || 12, r2 = +b.dataset.r || 12;
  const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const ax = x1 + ux * r1, ay = y1 + uy * r1;
  const bx = x2 - ux * r2, by = y2 - uy * r2;
  return {ax, ay, bx, by,
          mx: (ax + bx) / 2 - uy * bow, my: (ay + by) / 2 + ux * bow};
}
function draw() {
  const wires = document.getElementById("wires");
  if (!wires) return;
  wires.querySelectorAll("path[data-src]").forEach(p => {
    const a = document.getElementById(p.dataset.src);
    const b = document.getElementById(p.dataset.dst);
    if (!live(a) || !live(b)) { p.style.display = "none"; return; }
    p.style.display = "";
    const e = ends(a, b, +p.dataset.bow || 0);
    p.setAttribute("d", `M${e.ax},${e.ay} Q${e.mx},${e.my} ${e.bx},${e.by}`);
  });
  wires.querySelectorAll("text[data-src]").forEach(t => {
    const a = document.getElementById(t.dataset.src);
    const b = document.getElementById(t.dataset.dst);
    if (!live(a) || !live(b)) { t.style.display = "none"; return; }
    t.style.display = "";
    const e = ends(a, b, +t.dataset.bow || 0);
    const lx = (e.mx + (e.ax + e.bx) / 2) / 2, ly = (e.my + (e.ay + e.by) / 2) / 2;
    t.setAttribute("transform", `translate(${lx + 10},${ly})`);
    t.querySelectorAll("tspan").forEach(s => s.setAttribute("x", 0));
  });
  wires.querySelectorAll(".leader").forEach(l => l.remove());
  document.querySelectorAll(".frame[data-owner]").forEach(f => {
    if (f.style.display === "none" || f.closest(".body") ||
        f.classList.contains("hud")) return;
    const owner = document.getElementById(f.dataset.owner);
    if (!live(owner)) return;
    const ring = owner.closest(".nd.ring");
    const [rx, ry] = P(ring || owner);
    const ox = rx + (ring && ring !== owner ? parseFloat(owner.style.left) || 0 : 0);
    const oy = ry + (ring && ring !== owner ? parseFloat(owner.style.top) || 0 : 0);
    const [fx, fy] = P(f);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("class", "leader");
    path.setAttribute("d", `M${ox},${oy} L${fx},${fy + 14}`);
    wires.appendChild(path);
  });
}
// ── folding: what is above a ring collapses into one capsule ──
function applyFolds() {
  document.querySelectorAll(".capsule").forEach(c => c.remove());
  document.querySelectorAll(".folded").forEach(n =>
    n.classList.remove("folded", "hide"));
  folds.forEach(ident => {
    const at = document.getElementById(ident);
    if (!at) return;
    const cut = parseFloat(at.style.top) || 0;
    let count = 0, cx = null, cy = null;
    document.querySelectorAll(".nd.ring").forEach(ring => {
      if ((parseFloat(ring.style.top) || 0) >= cut) return;
      ring.classList.add("folded", "hide");
      count += 1;
      const [x, y] = P(ring);
      if (cy === null || y < cy) { cx = x; cy = y; }
    });
    if (!count) return;
    const cap = document.createElement("div");
    cap.className = "nd ring dim capsule";
    cap.dataset.capsule = ident;
    cap.style.left = cx + "px";
    cap.style.top = cy + "px";
    cap.innerHTML = '<div class="disc"></div><div class="core"></div>' +
      `<div class="title">${count} folded<span>click to unfold</span></div>`;
    world.appendChild(cap);
  });
  draw();
}
// ── the camera survives the world being replaced under it ──
function snapshot() {
  const state = {nodes: {}, frames: {}, tx, ty, scale, folds: [...folds]};
  document.querySelectorAll(".nd[id]").forEach(el => {
    state.nodes[el.id] = {left: el.style.left, top: el.style.top};
  });
  document.querySelectorAll(".frame[data-frame]").forEach(f => {
    state.frames[f.dataset.frame] = {
      left: f.style.left, top: f.style.top, width: f.style.width,
      height: f.style.height, display: f.style.display, z: f.style.zIndex,
      min: f.classList.contains("min"), geo: f.dataset.geo || "",
    };
  });
  return state;
}
function restore(state) {
  tx = state.tx; ty = state.ty; scale = state.scale;
  folds.clear(); state.folds.forEach(f => folds.add(f));
  Object.entries(state.nodes).forEach(([id, at]) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (at.left) el.style.left = at.left;
    if (at.top) el.style.top = at.top;
  });
  Object.entries(state.frames).forEach(([name, s]) => {
    const f = document.querySelector(`.frame[data-frame="${CSS.escape(name)}"]`);
    if (!f) return;
    if (s.left) f.style.left = s.left;
    if (s.top) f.style.top = s.top;
    if (s.width) f.style.width = s.width;
    if (s.height) f.style.height = s.height;
    f.style.display = s.display;
    if (s.z) f.style.zIndex = s.z;
    if (s.geo) f.dataset.geo = s.geo;
    f.classList.toggle("min", s.min);
    const moon = document.getElementById(f.dataset.owner || "");
    if (moon) moon.classList.toggle("on", s.display !== "none");
  });
  apply(); applyFolds();
}
// The camera frames what there is on arrival, and never again: after
// that, where things sit is the user's business.
function fit(pad) {
  const nodes = [...document.querySelectorAll(".nd")];
  if (!nodes.length) return;
  const xs = nodes.map(n => parseFloat(n.style.left) || 0);
  const ys = nodes.map(n => parseFloat(n.style.top) || 0);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const w = (x1 - x0) + 1200, h = (y1 - y0) + 340;
  scale = Math.min(1.05, (innerWidth - pad * 2) / w, (innerHeight - pad * 2) / h);
  tx = pad + 380 * scale - (x0 - 320) * scale;
  ty = (innerHeight - h * scale) / 2 - (y0 - 150) * scale;
  apply(); draw();
}
// Zoom to enter: bring one node to the middle at working scale, so its
// orbit is readable and its windows land in front of you. Not a mode —
// pan and wheel keep working, and drag a window anywhere you like. It
// is the camera doing what you would do by hand, in one gesture.
function enter(node, zoom) {
  const [nx, ny] = P(node);
  const want = zoom === undefined ? 1.0 : zoom;
  const from = {scale, tx, ty};
  const to = {
    scale: want,
    tx: innerWidth * 0.28 - nx * want,
    ty: innerHeight * 0.45 - ny * want,
  };
  glide(from, to, 260);
}
// One easing, so every camera move feels like the same camera.
function glide(from, to, ms) {
  const t0 = performance.now();
  const step = now => {
    const k = Math.min(1, (now - t0) / ms);
    const e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    scale = from.scale + (to.scale - from.scale) * e;
    tx = from.tx + (to.tx - from.tx) * e;
    ty = from.ty + (to.ty - from.ty) * e;
    apply(); draw();
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
// Double-click the void to see everything again — the way out is the
// same size gesture as the way in.
space.addEventListener("dblclick", e => {
  const node = e.target.closest(".nd.ring");
  if (node) { enter(node); return; }
  if (!e.target.closest(".frame")) fit(90);
});
// A window is born beside its node and stays with it until somebody
// puts it somewhere. The server draws it at the node's LAID-OUT spot,
// which is wrong the moment the node is dragged — so where it opens is
// decided here, against where its node actually is.
function beside(f) {
  if (f.dataset.placed) return;
  const moon = document.getElementById(f.dataset.owner || "");
  const ring = moon ? moon.closest(".nd.ring") : null;
  if (!ring) return;
  const [rx, ry] = P(ring);
  const kin = [...document.querySelectorAll(`.frame[data-owner^="m-${ring.id}-"]`)];
  const slot = Math.max(0, kin.indexOf(f));
  f.style.left = (rx + 250 + slot * 26) + "px";
  f.style.top = Math.max(60, ry - 60 + slot * 44) + "px";
}
window.opsisBeside = beside;
function toggle(name) {
  const f = document.querySelector(`.frame[data-frame="${CSS.escape(name)}"]`);
  if (!f) return null;
  const open = f.style.display === "none";
  f.style.display = open ? "flex" : "none";
  if (open) {
    f.style.zIndex = ++zTop;
    if (window.opsisFill) window.opsisFill(f);
    // A window opened INSIDE another lands where that window is looking,
    // so its own chrome is never scrolled out of reach.
    const host = f.parentElement && f.parentElement.closest(".body");
    if (host) {
      f.style.left = (host.scrollLeft + 24) + "px";
      f.style.top = (host.scrollTop + 24) + "px";
    } else {
      beside(f);
    }
  }
  const moon = document.getElementById(f.dataset.owner || "");
  if (moon) moon.classList.toggle("on", open);
  draw();
  return f;
}
window.opsisCamera = {snapshot, restore, draw, fit, toggle, enter,
                      raise: el => { el.style.zIndex = ++zTop; }};
space.addEventListener("wheel", e => {
  if (e.target.closest(".frame")) return;
  e.preventDefault();
  const k = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  tx = e.clientX - (e.clientX - tx) * k;
  ty = e.clientY - (e.clientY - ty) * k;
  scale *= k; apply();
}, {passive: false});
document.addEventListener("pointerdown", e => {
  const f = e.target.closest(".frame");
  if (f) f.style.zIndex = ++zTop;
  const t = e.target;
  if (t.classList.contains("close")) {
    f.style.display = "none";
    const moon = document.getElementById(f.dataset.owner || "");
    if (moon) moon.classList.remove("on");
    draw(); return;
  }
  if (t.classList.contains("min")) { f.classList.toggle("min"); draw(); return; }
  if (t.classList.contains("max")) {
    // Computed against the viewport now, so maximizing means the same
    // thing however far the camera has been panned or zoomed.
    if (f.dataset.geo) {
      const g = JSON.parse(f.dataset.geo);
      delete f.dataset.geo;
      f.style.left = g.l; f.style.top = g.t;
      f.style.width = g.w; f.style.height = g.h;
    } else {
      f.dataset.geo = JSON.stringify({l: f.style.left, t: f.style.top,
                                      w: f.style.width, h: f.style.height});
      const m = 30, hud = f.classList.contains("hud"), k = hud ? 1 : scale;
      if (!hud) {
        f.style.left = ((m - tx) / scale) + "px";
        f.style.top = ((m - ty) / scale) + "px";
      }
      f.style.width = ((innerWidth - 2 * m) / k) + "px";
      f.style.height = ((innerHeight - 2 * m) / k) + "px";
    }
    draw(); return;
  }
  if (t.classList.contains("grip")) {
    const p = P(f);
    f.dataset.placed = "1";
    drag = {kind: "size", el: f, side: t.dataset.side,
            sx: e.clientX, sy: e.clientY,
            w: f.offsetWidth, h: f.offsetHeight, x: p[0], y: p[1],
            fixed: f.classList.contains("hud")};
    hold(t, e);
    return;
  }
  if (t.closest(".act, .moon")) return;   // affordances are clicks, not drags
  const capsule = t.closest(".capsule");
  if (capsule) { folds.delete(capsule.dataset.capsule); applyFolds(); return; }
  const header = t.closest(".frame header");
  const node = t.closest(".nd");
  if (header || node) hold(t, e);
  if (header) {
    if (f.classList.contains("hud") && !f.style.left) {
      const r = f.getBoundingClientRect();
      f.style.left = r.left + "px"; f.style.top = r.top + "px";
      f.style.transform = "none";
    }
    f.dataset.placed = "1";   // put here on purpose; stop following the node
    drag = {kind: "move", el: f, sx: e.clientX, sy: e.clientY,
            x: P(f)[0], y: P(f)[1], fixed: f.classList.contains("hud")};
  } else if (node && !f) {
    drag = {kind: "move", el: node, sx: e.clientX, sy: e.clientY,
            x: P(node)[0], y: P(node)[1], moved: false};
  } else if (!f && !node && t.closest("#space")) {
    panning = {x: e.clientX - tx, y: e.clientY - ty};
    space.classList.add("dragging");
  }
});
// A window taken by its left or top edge grows the other way: the
// side you did NOT grab is the one that must not move.
function size(d, dx, dy) {
  const s = d.side || "se";
  const W = 240, H = 64;
  let w = d.w, h = d.h, x = d.x, y = d.y;
  if (s.includes("e")) w = Math.max(W, d.w + dx);
  if (s.includes("s")) h = Math.max(H, d.h + dy);
  if (s.includes("w")) { w = Math.max(W, d.w - dx); x = d.x + (d.w - w); }
  if (s.includes("n")) { h = Math.max(H, d.h - dy); y = d.y + (d.h - h); }
  d.el.style.width = w + "px";
  d.el.style.height = h + "px";
  if (!d.fixed || d.el.style.left) { d.el.style.left = x + "px"; d.el.style.top = y + "px"; }
}
// Capture the pointer so a fast drag cannot outrun its own handle.
function hold(el, e) {
  if (el.setPointerCapture) el.setPointerCapture(e.pointerId);
  document.body.classList.add("dragging-any");
}
addEventListener("pointermove", e => {
  if (panning) { tx = e.clientX - panning.x; ty = e.clientY - panning.y; apply(); return; }
  if (!drag) return;
  const k = drag.fixed ? 1 : scale;
  const dx = (e.clientX - drag.sx) / k, dy = (e.clientY - drag.sy) / k;
  if (Math.hypot(dx, dy) > 3) drag.moved = true;
  if (drag.kind === "size") { size(drag, dx, dy); draw(); return; }
  let nx = drag.x + dx, ny = drag.y + dy;
  const host = drag.el.parentElement && drag.el.parentElement.closest(".body");
  if (host && drag.el.classList.contains("frame")) {
    nx = Math.max(host.scrollLeft, nx); ny = Math.max(host.scrollTop, ny);
  }
  drag.el.style.left = nx + "px"; drag.el.style.top = ny + "px";
  if (drag.el.classList.contains("ring")) {
    document.querySelectorAll(".landing").forEach(n => n.classList.remove("landing"));
    const over = window.opsisLanding &&
                 window.opsisLanding(drag.el, e.clientX, e.clientY);
    if (over) over.classList.add("landing");
  }
  draw();
});
addEventListener("pointerup", e => {
  panning = null; space.classList.remove("dragging");
  document.body.classList.remove("dragging-any");
  document.querySelectorAll(".landing").forEach(n => n.classList.remove("landing"));
  if (drag && drag.moved && drag.el.classList.contains("ring") && window.opsisDrop) {
    window.opsisDrop(drag.el, e.clientX, e.clientY);
  }
  drag = null;
});
document.addEventListener("click", e => {
  const group = e.target.closest(".moon[data-orbit]");
  if (group && !e.target.closest(".moon.inner")) {
    // A group opens in place. Only one at a time on a ring: two open
    // orbits overlap, and an unreadable fan is not a fan.
    const ring = group.closest(".nd.ring");
    const was = group.classList.contains("open");
    if (ring) ring.querySelectorAll(".moon.group.open")
                  .forEach(o => o.classList.remove("open"));
    group.classList.toggle("open", !was);
    draw();
    return;
  }
  const moon = e.target.closest(".moon[data-open]");
  if (moon) { toggle(moon.dataset.open); return; }
  const opener = e.target.closest("[data-open]:not(.moon)");
  if (opener) { const f = toggle(opener.dataset.open); if (f) f.style.zIndex = ++zTop; return; }
  const fold = e.target.closest(".act.fold");
  if (fold) { folds.add(fold.closest(".nd.ring").id); applyFolds(); }
});
document.addEventListener("pointerover", e => {
  const t = e.target.closest("[data-rule]");
  document.querySelectorAll(".dx").forEach(n => n.classList.remove("dx"));
  if (!t) return;
  document.querySelectorAll(`[data-rule="${CSS.escape(t.dataset.rule)}"]`)
    .forEach(n => n.classList.add("dx"));
});
apply(); draw(); fit(90);
"""
"""The camera — DOM behavior only. The scene never moves."""


def page(scene: Space, subtitle: str = "", world: str = "", hud: str = "") -> str:
    """A complete page for one scene.

    ``world`` is markup inside ``#world`` (it pans and zooms with
    everything else); ``hud`` holds still. Deterministic: the same scene
    renders the same bytes, which is what makes a page comparable
    across freeze and thaw.
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
                el("title", None, "opsis"),
                el("style", None, raw(css())),
            ),
            el(
                "body",
                None,
                el(
                    "div",
                    {"id": "hud"},
                    el("h1", None, "opsis"),
                    el("p", None, subtitle),
                ),
                el(
                    "div",
                    {"id": "space"},
                    el("div", {"id": "world"}, raw(render_scene(scene)), raw(world)),
                ),
                raw(hud),
                el("script", None, raw(CAMERA)),
            ),
        ),
    )
    return html(doc)
