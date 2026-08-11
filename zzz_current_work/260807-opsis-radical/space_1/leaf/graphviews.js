/* opsis leaf — the rule-graph views — flat, arcs, 3d.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── the rule-graph views: flat · arcs · 3d — drawn from the IR in hand ── */

function bootGraphViews(scope) {
  for (const view of scope.querySelectorAll('.gview')) {
    if (view.dataset.armed) continue;
    view.dataset.armed = '1';
    view._cam = { yaw: 0.6, pitch: 0.45, zoom: 1 };
    view._mode = 'flat';
    fetch(`/rulegraph?place=${encodeURIComponent(view.dataset.place)}`)
      .then((r) => r.text()).then((text) => {
        const nodes = [], edges = [];
        for (const line of text.split('\n').slice(1)) {
          const p = line.split(' ');
          if (p[0] === 'n') nodes.push({ name: p[1], order: +p[2], depth: +p[3] });
          else if (p[0] === 'e') edges.push([p[1], p[2]]);
        }
        view._g = { nodes, edges };
        pvDrawView(view);
      });
    armGraphView(view);
  }
}

function armGraphView(view) {
  const canvas = view.querySelector('canvas');
  view.addEventListener('click', (ev) => {
    const tab = ev.target.closest('.gtab');
    if (!tab) return;
    view._mode = tab.dataset.view;
    for (const b of view.querySelectorAll('.gtab')) b.classList.toggle('on', b === tab);
    pvDrawView(view);
  });
  let drag = null;
  canvas.addEventListener('pointerdown', (ev) => {
    if (view._mode !== '3d') return;
    drag = { x: ev.clientX, y: ev.clientY };
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    view._cam.yaw += (ev.clientX - drag.x) * 0.008;
    view._cam.pitch = Math.max(-1.4, Math.min(1.4,
      view._cam.pitch + (ev.clientY - drag.y) * 0.006));
    drag = { x: ev.clientX, y: ev.clientY };
    pvDrawView(view);
  });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('wheel', (ev) => {
    if (view._mode !== '3d') return;
    ev.preventDefault();
    view._cam.zoom = Math.max(0.3, Math.min(4,
      view._cam.zoom * (ev.deltaY < 0 ? 1.1 : 0.9)));
    pvDrawView(view);
  }, { passive: false });
}

const GV_INK = '#d7dde7', GV_DIM = '#7d8794', GV_WIRE = '#39414f', GV_WARM = '#f0b25e';

function gvPaint(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || canvas.parentElement.clientWidth || 700;
  const h = 400;
  canvas.style.height = `${h}px`;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  ctx.font = '10px monospace';
  return { ctx, w, h };
}

function pvDrawView(view) {
  if (!view._g) return;
  const { ctx, w, h } = gvPaint(view.querySelector('canvas'));
  if (view._mode === 'flat') gvFlat(ctx, w, h, view._g);
  else if (view._mode === 'arcs') gvArcs(ctx, w, h, view._g);
  else gv3d(ctx, w, h, view._g, view._cam);
}

function gvFlat(ctx, w, h, g) {
  const maxDepth = Math.max(...g.nodes.map((n) => n.depth).filter((d) => d < 99), 0);
  const lanes = new Map();
  for (const n of [...g.nodes].sort((a, b) => a.order - b.order)) {
    const d = Math.min(n.depth, maxDepth + 1);
    if (!lanes.has(d)) lanes.set(d, []);
    lanes.get(d).push(n);
  }
  const pos = new Map();
  const colW = (w - 60) / (maxDepth + 2);
  for (const [depth, lane] of lanes) {
    lane.forEach((n, i) => pos.set(n.name, {
      x: 30 + depth * colW,
      y: 22 + (h - 44) * (lane.length === 1 ? 0.5 : i / (lane.length - 1)) }));
  }
  ctx.strokeStyle = GV_WIRE;
  for (const [a, b] of g.edges) {
    const p = pos.get(a), q = pos.get(b);
    if (!p || !q) continue;
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.bezierCurveTo((p.x + q.x) / 2, p.y, (p.x + q.x) / 2, q.y, q.x, q.y);
    ctx.stroke();
  }
  for (const n of g.nodes) {
    const p = pos.get(n.name);
    if (!p) continue;
    ctx.fillStyle = n.depth === 0 ? GV_WARM : GV_INK;
    ctx.fillRect(p.x - 2, p.y - 2, 4, 4);
    ctx.fillStyle = n.depth === 0 ? GV_WARM : GV_DIM;
    ctx.fillText(n.name, p.x + 5, p.y + 3);
  }
}

function gvArcs(ctx, w, h, g) {
  const sorted = [...g.nodes].sort((a, b) => a.order - b.order);
  const base = h * 0.6;
  const step = (w - 60) / Math.max(1, sorted.length - 1);
  const pos = new Map();
  sorted.forEach((n, i) => pos.set(n.name, { x: 30 + i * step, i }));
  ctx.strokeStyle = GV_WIRE;
  for (const [a, b] of g.edges) {
    const p = pos.get(a), q = pos.get(b);
    if (!p || !q || a === b) continue;
    const up = q.i > p.i;
    const span = Math.abs(q.x - p.x);
    ctx.beginPath();
    ctx.moveTo(p.x, base);
    ctx.quadraticCurveTo((p.x + q.x) / 2,
      base + (up ? -1 : 1) * Math.min(base - 14, 18 + span * 0.3), q.x, base);
    ctx.stroke();
  }
  for (const n of sorted) {
    const p = pos.get(n.name);
    ctx.fillStyle = n.depth === 0 ? GV_WARM : GV_INK;
    ctx.fillRect(p.x - 2, base - 2, 4, 4);
    ctx.save();
    ctx.translate(p.x + 3, base + 10);
    ctx.rotate(Math.PI / 3);
    ctx.fillStyle = n.depth === 0 ? GV_WARM : GV_DIM;
    ctx.fillText(n.name, 0, 0);
    ctx.restore();
  }
}

function gv3d(ctx, w, h, g, cam) {
  const levels = new Map();
  for (const n of [...g.nodes].sort((a, b) => a.order - b.order)) {
    if (!levels.has(n.depth)) levels.set(n.depth, []);
    levels.get(n.depth).push(n);
  }
  const step = 80;
  const world = new Map();
  for (const [depth, lane] of levels) {
    const radius = lane.length === 1 ? 0 : 40 + 28 * Math.sqrt(lane.length);
    lane.forEach((n, i) => {
      const angle = (i / lane.length) * Math.PI * 2;
      world.set(n.name, { x: radius * Math.cos(angle),
                          y: radius * Math.sin(angle), z: depth * step, d: n.depth });
    });
  }
  const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
  const proj = new Map();
  for (const [name, p] of world) {
    const x1 = p.x * cy + (p.z - step) * sy;
    const z1 = -p.x * sy + (p.z - step) * cy;
    const y1 = p.y * cp - z1 * sp;
    const z2 = p.y * sp + z1 * cp;
    const s = 420 / (420 + z2 + 240);
    proj.set(name, { x: x1 * s, y: y1 * s, z: z2, s, d: p.d });
  }
  // auto-fit AFTER projection: the orbit changes the extent, so a fixed
  // scale throws the graph off-screen on rotation (the reported break)
  let x0 = 1e9, x1m = -1e9, y0 = 1e9, y1m = -1e9;
  for (const P of proj.values()) {
    x0 = Math.min(x0, P.x); x1m = Math.max(x1m, P.x);
    y0 = Math.min(y0, P.y); y1m = Math.max(y1m, P.y);
  }
  const k = Math.min((w * 0.86) / Math.max(40, x1m - x0),
                     (h * 0.82) / Math.max(40, y1m - y0)) * cam.zoom;
  const mx = (x0 + x1m) / 2, my = (y0 + y1m) / 2;
  for (const P of proj.values()) {
    P.x = w / 2 + (P.x - mx) * k;
    P.y = h / 2 + (P.y - my) * k;
  }
  ctx.strokeStyle = GV_WIRE;
  for (const [a, b] of g.edges) {
    const p = proj.get(a), q = proj.get(b);
    if (!p || !q) continue;
    ctx.globalAlpha = Math.max(0.25, Math.min(1, p.s));
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(q.x, q.y);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (const [name, p] of [...proj.entries()].sort((a, b) => b[1].z - a[1].z)) {
    const r = Math.max(1.6, 3.2 * p.s);
    ctx.fillStyle = p.d === 0 ? GV_WARM : GV_INK;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
    if (p.s > 0.55 || p.d === 0) {
      ctx.fillStyle = p.d === 0 ? GV_WARM : GV_DIM;
      ctx.fillText(name, p.x + r + 2, p.y + 3);
    }
  }
}

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const layer = $('strata');
  if (layer && layer.classList.contains('on')) {
    e.stopPropagation();
    closeStrata();
  }
}, true);


async function pollRoutes() {
  const text = await (await fetch('/routes')).text();
  const r = {};
  for (const line of text.split('\n')) {
    const k = line.slice(0, line.indexOf(' '));
    r[k] = line.slice(k.length + 1);
  }
  const el = $('routes');
  if (r.status === 'pending') {
    el.textContent = ` · route: ${r.primary} ${r.primary_seconds}s · the other engine is running…`;
    setTimeout(pollRoutes, 1200);
  } else if (r.status === 'done') {
    el.textContent = ` · route: ${r.primary} ${r.primary_seconds}s · ${r.name} ${r.seconds}s · `
      + (r.parity === 'holds' ? 'both engines built the same value — holds'
         : r.parity === 'unmeasured' ? 'parity unmeasured' : 'PARITY FAILS');
    el.className = r.parity === 'holds' ? 'holds' : '';
  } else {
    const pos = parseInt(r.pos ?? '-1', 10);
    el.textContent = ` · route: ${r.primary} ${r.primary_seconds}s · ${r.name} ended`
      + (pos >= 0 ? ` at char ${pos.toLocaleString()} — where the fast road stops` : `: ${r.words}`);
  }
}

(async () => {
  wireGraph();  // the facet view must exist before boot applies reader.mode/camera policy
  await boot(false);
  wire();
  wirePins();
  wireChip();
  wireTransport();
  wireSpineZoom();
  wireTextZoom();
  wireChartZoom();
  wireClockSelect();
  wireFacetDrops();
  wireRailChip();
  wireTune();
  wireSeams();
  pollRoutes();
  pollPolicy();
  const q = new URLSearchParams(location.search);
  if (q.has('t')) { cur.t = Math.min(+q.get('t'), S.doc.length); cur.follow = true; ask(); }
  if (q.has('sel')) {
    cur.sel = deepestAt(+q.get('sel'));
    render();
    if (cur.sel >= 0) chipAt(S.spans[cur.sel].s, true);
  }
  if (q.has('rule')) { cur.rule = q.get('rule'); ask(); }
  if (q.has('break')) { const off = +q.get('break'); applyEdit(off, off + 1, '\u00a7'); }
  if (q.has('pin')) {
    for (const off of q.get('pin').split(',')) addPin(deepestAt(+off));
  }
  if (q.has('graph')) setGraph(true);
  if (q.has('gpin')) { setGraph(true); graphPin(); }
  if (q.has('rail')) { for (const name of q.get('rail').split(',')) railPin(name); }
  if (q.has('focus')) { focusOn = true; $('gfocus').classList.add('on'); drawGraph(); }
  if ([...q.keys()].length === 0) setTimeout(play, 600);  // deterministic states do not animate
})();

const _q = new URLSearchParams(location.search);
if (_q.has('strata')) setTimeout(openStrata, 700);
if (_q.has('place')) setTimeout(() => openPlace(_q.get('place')), 900);
if (_q.has('rooms')) setTimeout(() => openPlace('index'), 900);
document.addEventListener('click', (e) => {
  if (e.target && e.target.id === 'placeBack') closePlace();
});
