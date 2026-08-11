/* opsis leaf — the 3D rule graph.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── the 3D rule graph — z is derivation distance, the earned axis ── */

// the relations facet is open by default: it is a surface, not a mode
let graphOn = true;
let gNodes = null;
let graphHover = '';
let gViews = [];  // [0] is the facet view; others live inside pinned windows
let gLevels = new Map();

function viewMode(v) { return v.pin ? (v.pin.mode || 'depth3d') : gView; }

function switchViewMode(v, from, to) {
  if (from === to) return;
  v.cams = v.cams || {};
  v.cams[from] = { yaw: v.yaw, pitch: v.pitch, zoom: v.zoom, pan: { ...v.pan }, touched: v.touched };
  const c = v.cams[to];
  if (c) Object.assign(v, { yaw: c.yaw, pitch: c.pitch, zoom: c.zoom, pan: { ...c.pan }, touched: c.touched });
  else Object.assign(v, { yaw: 0.42, pitch: 0.92, zoom: 1, pan: { x: 0, y: 0 }, touched: false });
  v.fit = null;
}

function makeGraphView(wrap, cv, chips) {
  return { wrap, cv, chips, yaw: 0.42, pitch: 0.92, zoom: 1, pan: { x: 0, y: 0 }, touched: false };
}

function markedRule() { return cur.rule || graphHover; }

// WHAT IS LIVE AT t — the spans open at the cursor, which is the derivation's
// own stack. The automaton lit itself from the PDA's frames and nothing else
// lit at all, so playing the derivation animated one view out of five.

function liveRules() {
  // what is live comes from the POINT the reading answered with — one
  // resolution, shared by every surface, instead of three scans that could
  // disagree with each other
  return new Set(pointHere.lit);
}

function livePath() { return pointHere.open.map((r) => r.rule); }

function liveEdge(a, b) {
  // an edge is live when it is a STEP the derivation is standing on: one
  // open rule directly inside the next. Lighting every edge between two
  // live rules would light the whole grammar at depth.
  const path = livePath();
  for (let i = 0; i + 1 < path.length; i++) {
    if (path[i] === a && path[i + 1] === b) return true;
  }
  return false;
}

function hotRule() {
  if (graphHover) return graphHover;
  if (cur.hover >= 0) return S.ruleNames[S.spans[cur.hover].r];
  return '';
}

function ruleDef(name) {
  if (S.ruleOf[name]) return S.ruleOf[name];
  const ci = S.ruledefs.find((r) => r.name.toLowerCase() === name.toLowerCase());
  return ci ? { a: ci.a, b: ci.b } : null;
}

// Positions ARRIVE. The ring maths, the band wrapping and the
// declaration-order row all lived here and were derivation, not drawing —
// the one kind of logic a fact cannot reach. The leaf now asks for a view
// and paints what comes back; the camera stays here, because the camera is
// the hand's, not the reading's.
let placedFor = '';

function graphBox() {
  const wrap = $('graphWrap');
  const w = Math.max(320, wrap ? wrap.clientWidth : 900);
  const h = Math.max(240, wrap ? wrap.clientHeight : 600);
  return `${Math.round(w)}x${Math.round(h)}`;
}

function viewName(mode) { return mode === 'depth3d' ? 'rings' : mode; }

async function loadPlaces(mode = gView, force = false) {
  const view = viewName(mode);
  if (view !== 'flat' && view !== 'arcs' && view !== 'rings') return;
  const key = `${view}|${graphBox()}|${S.meta.generation}|${S.policy.form || ''}`;
  if (!force && key === placedFor) return;
  placedFor = key;
  const text = await (await fetch(
    `/rulegraph?view=${view}&box=${graphBox()}`)).text();
  const places = new Map();
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].startsWith('#PLACES ')) continue;
    const n = parseInt(lines[i].split(' ')[1], 10) || 0;
    for (const row of lines.slice(i + 1, i + 1 + n)) {
      const p = row.split(' ');
      places.set(p.slice(3).join(' '), { x: +p[0], y: +p[1], z: +p[2] });
    }
    break;
  }
  if (!places.size) return;
  gNodes = places;
  gRecentre();
  buildChipsInto(gViews[0] ? gViews[0].chips : $('graphChips'));
  for (const v of gViews) if (v.chips) buildChipsInto(v.chips);
  drawGraph();
}

function buildGraph() { loadPlaces(gView, true); }

function buildChipsInto(chips) {
  chips.textContent = '';
  for (const name of gNodes.keys()) {
    const el = document.createElement('span');
    el.className = 'gchip';
    el.dataset.name = name;
    el.textContent = name;
    chips.appendChild(el);
  }
}

// How far away the eye stands. A fixed focal length means a big grammar
// swings a long way toward the camera as it turns, and the whole picture
// pumps — badly on the metagrammar, whose rings are wide. So the distance
// is derived from the layout's own reach, which bounds how much nearness
// can change a node's size no matter how far you rotate.
let gDepth = { reach: 0, focal: 900 };
let gCentre = { x: 0, y: 0, z: 0 };

function gRecentre() {
  // a layout whose middle is not the origin orbits around a point outside
  // itself: it swings across the panel and sits off-centre at rest. The
  // depth axis runs 0..−N, so this was the whole picture hanging low.
  let n = 0, sx = 0, sy = 0, sz = 0;
  for (const [, p] of gNodes || []) { n++; sx += p.x; sy += p.y; sz += p.z; }
  gCentre = n ? { x: sx / n, y: sy / n, z: sz / n } : { x: 0, y: 0, z: 0 };
}

function gFocal() {
  if (!gNodes) return gDepth.focal;
  let reach = 0;
  for (const [, p] of gNodes) {
    reach = Math.max(reach, Math.hypot(p.x - gCentre.x, p.y - gCentre.y,
                                       p.z - gCentre.z));
  }
  if (reach !== gDepth.reach) {
    // near/far no wider than ~1.25:1 — depth still reads, size stays put
    gDepth = { reach, focal: Math.max(900, reach * 9) };
  }
  return gDepth.focal;
}

function gProject(v, p, w, h) {
  const px = p.x - gCentre.x, py = p.y - gCentre.y, pz = p.z - gCentre.z;
  const cy = Math.cos(v.yaw), sy = Math.sin(v.yaw);
  const x = px * cy + pz * sy;
  let z = -px * sy + pz * cy;
  const cp = Math.cos(v.pitch), sp = Math.sin(v.pitch);
  const y = py * cp - z * sp;
  z = py * sp + z * cp;
  const f = gFocal();
  const s = f / Math.max(f * 0.4, f - z);   // no pole, no mirror
  return { x: w / 2 + x * s, y: h / 2 + y * s, s };
}

function drawGraph() {
  for (const p of pins) {
    if (p.kind === 'rail' && p.tree && p.el && document.contains(p.el)) drawRailPin(p, p.el);
  }
  if (!gNodes) return;
  for (const v of gViews) {
    if (!document.contains(v.wrap) || v.wrap.closest('[hidden]')) continue;
    drawGraphView(v);
  }
}

function drawGraphView(v, smooth = false) {
  const mode = viewMode(v);
  if (mode === 'text') return;
  if (mode === 'rails') { drawRailsView(v); return; }
  if (mode === 'automaton') { drawAutoView(v); return; }
  v.chips.style.display = '';
  const wrap = v.wrap;
  const cv = v.cv;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w || !h) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const cx = cv.getContext('2d');
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  const proj = new Map();
  if (mode === 'depth3d') {
    // the camera is the hand's: the reading gives a place in 3-space, the
    // camera says where you are standing to look at it
    for (const [name, p] of gNodes) proj.set(name, gProject(v, p, w, h));
  } else {
    for (const [name, p] of gNodes) proj.set(name, { x: p.x, y: p.y, s: 1 });
  }
  // auto-fit: fill the facet whatever the grammar's size or the orbit's angle
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  for (const P of proj.values()) {
    x0 = Math.min(x0, P.x); x1 = Math.max(x1, P.x);
    y0 = Math.min(y0, P.y); y1 = Math.max(y1, P.y);
  }
  // fit against the LABELS, not the dots. A node centred one pixel inside
  // the edge still hangs its name over the side, and a crowded level lost
  // every name at the rim — which is the "graph crops out" everyone sees.
  let padX = 10, padY = 10;
  for (const el of v.chips.children) {
    padX = Math.max(padX, el.offsetWidth / 2 + 4);
    padY = Math.max(padY, el.offsetHeight / 2 + 4);
  }
  const availW = Math.max(60, w - 2 * padX), availH = Math.max(60, h - 2 * padY);
  // The fit belongs to the LAYOUT AND THE ROOM, not to the camera's angle.
  // Refitting the projected extent every frame meant the picture breathed
  // in and out as you rotated it: the same graph, rescaled because its
  // silhouette got narrower. A camera moves within a frame; it is not the
  // frame. So the fit is computed once per layout and per box, and the
  // angle changes nothing about it.
  const frameKey = `${placedFor}|${mode}|${Math.round(w)}x${Math.round(h)}`;
  if (v.frameKey !== frameKey || !v.frame) {
    v.frameKey = frameKey;
    if (mode === 'depth3d') {
      // A BOUND, not a sample. Whatever the yaw and pitch, a node's
      // projected offset cannot exceed its distance from the axis it turns
      // around — so the frame that holds one angle holds every angle.
      // Sampling four of them left the widest silhouettes (which fall
      // between samples) hanging over the edge, and the picture appeared to
      // zoom as it turned.
      let radial = 0, vertical = 0, near = 0;
      for (const [, p] of gNodes) {
        const dx = p.x - gCentre.x, dy = p.y - gCentre.y, dz = p.z - gCentre.z;
        radial = Math.max(radial, Math.hypot(dx, dz));
        vertical = Math.max(vertical, Math.hypot(dy, dz));
        near = Math.max(near, Math.hypot(dx, dy, dz));
      }
      const f = gFocal();
      const closest = f / Math.max(f * 0.4, f - near);   // the biggest scale
      v.frame = {
        k: Math.min(
          availW / Math.max(40, 2 * radial * closest),
          availH / Math.max(40, 2 * vertical * closest),
          2.4,
        ),
        mx: 0,
        my: 0,
      };
    } else {
      v.frame = {
        k: Math.min(availW / Math.max(40, x1 - x0),
                    availH / Math.max(40, y1 - y0), 2.4),
        mx: (x0 + x1) / 2,
        my: (y0 + y1) / 2,
      };
    }
  }
  v.fitScale = v.frame.k;
  const k = v.frame.k * v.zoom;
  // the centre is the LAYOUT's, held still. Re-centring on the projected
  // silhouette every frame slides the picture under the hand as it turns,
  // which reads as zooming even when the scale never moved.
  // the projection already centres itself on the canvas, so the fixed
  // centre for an orbit is that centre — not the origin, which would place
  // the whole picture a screen's width away
  const mx = mode === 'depth3d' ? w / 2 : v.frame.mx;
  const my = mode === 'depth3d' ? h / 2 : v.frame.my;
  // frame the start rule's edge ONLY when the picture is wider than the
  // room — then panning is how you explore it. When it already fits, this
  // shoved the fitted picture sideways and pushed its far edge back out.
  if (mode !== 'depth3d' && !v.touched && (x1 - x0) * k > availW + 2) {
    v.pan.x = 70 - w / 2 - (x0 - mx) * k;
  }
  for (const P of proj.values()) {
    P.x = w / 2 + (P.x - mx) * k + v.pan.x;
    P.y = h / 2 + (P.y - my) * k + v.pan.y;
  }
  const mark = markedRule();
  const keepE = focusSet();
  for (const [a, b] of S.edges) {
    const A = proj.get(a), B = proj.get(b);
    if (!A || !B) continue;
    if (keepE !== null && !(keepE.has(a) && keepE.has(b))) continue;
    const touched = mark && (a === mark || b === mark);
    cx.strokeStyle = liveEdge(a, b)
      ? 'rgba(226,166,92,0.9)'
      : touched
        ? 'rgba(217,140,245,0.75)'
        : `rgba(111,195,201,${(0.06 + 0.22 * Math.min(A.s, B.s)).toFixed(3)})`;
    cx.lineWidth = liveEdge(a, b) ? 2 : 1;
    cx.beginPath();
    if (mode === 'arcs' && a !== b) {
      const dir = B.x >= A.x ? 1 : -1;  // forward references arc above, backward below
      const lift = dir * (12 + Math.abs(B.x - A.x) * 0.28) * gTune.ringscale;
      cx.moveTo(A.x, A.y);
      cx.quadraticCurveTo((A.x + B.x) / 2, A.y - lift, B.x, B.y);
    } else if (mode === 'arcs') {
      cx.arc(A.x, A.y - 9, 7, 0, Math.PI * 2);  // recursion: a self-loop ring
    } else {
      cx.moveTo(A.x, A.y);
      cx.lineTo(B.x, B.y);
    }
    cx.stroke();
  }
  const start = Object.keys(S.depths).find((n) => S.depths[n] === 0) || '';
  const hot = hotRule();
  const live = liveRules();
  const keep = focusSet();
  for (const el of v.chips.children) {
    const P = proj.get(el.dataset.name);
    if (!P) continue;
    el.style.left = P.x + 'px';
    el.style.top = P.y + 'px';
    el.style.transform = `translate(-50%, -50%) scale(${Math.max(0.55, Math.min(P.s, 1.2)).toFixed(2)})`;
    el.style.zIndex = Math.round(P.s * 1000);
    el.style.display = '';
    el.classList.toggle('near', mode === 'depth3d' ? P.s > 0.85 : true);
    el.classList.toggle('dot', mode === 'arcs'
      && el.dataset.name !== hot && el.dataset.name !== cur.rule && el.dataset.name !== start);
    el.classList.toggle('start', el.dataset.name === start);
    el.classList.toggle('marked', el.dataset.name === cur.rule);
    el.classList.toggle('hot', el.dataset.name === hot);
    el.classList.toggle('live', live.has(el.dataset.name));
    el.classList.toggle('faded', keep !== null && !keep.has(el.dataset.name));
  }
}

function setGraph(on, fromPolicy = false) {
  // the relations are their OWN facet now. Living inside the reader, the
  // graph could only appear by hiding the grammar it is a picture of, and
  // it inherited a column measured for text — which is the placement
  // failure this whole build exists to stop making.
  graphOn = on;
  facetOn['graph'] = on;
  if (!fromPolicy) postPolicy('facet.graph', on ? 'on' : 'off');
  applyFacets();
  if (on && !gNodes) buildGraph();
  if (on) drawGraph();
}

function wireGraphView(v) {
  let drag = null;
  v.wrap.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.gchip') || e.target.closest('#gtune')) return;
    if (viewMode(v) === 'text') return;
    v.dragMoved = false;
    drag = { x: e.clientX, y: e.clientY, pan: viewMode(v) !== 'depth3d' || e.shiftKey };
    e.preventDefault();
  });
  window.addEventListener('pointermove', (e) => {
    if (!drag) return;
    if (drag.pan) {
      v.touched = true;
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 2) v.dragMoved = true;
      v.pan.x += e.clientX - drag.x;
      v.pan.y += e.clientY - drag.y;
      drag = { x: e.clientX, y: e.clientY, pan: true };
      drawGraphView(v);
      return;
    }
    v.yaw += (e.clientX - drag.x) * 0.006;
    v.pitch = Math.max(-1.4, Math.min(1.4, v.pitch + (e.clientY - drag.y) * 0.005));
    drag = { x: e.clientX, y: e.clientY };
    drawGraphView(v, true);
  });
  window.addEventListener('pointerup', () => {
    if (drag) persistView(v);
    drag = null;
  });
  v.wrap.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (viewMode(v) === 'rails' && !e.ctrlKey) {
      // a stack of diagrams reads like a document: wheel scrolls, Ctrl+wheel zooms
      v.touched = true;
      v.pan.y -= e.deltaY;
      persistView(v);
      drawGraphView(v);
      return;
    }
    const r = v.wrap.getBoundingClientRect();
    const factorTo = Math.max(0.35, Math.min(5, v.zoom * Math.pow(1.0016, -e.deltaY)));
    const factor = factorTo / v.zoom;
    v.zoom = factorTo;
    v.touched = true;
    // anchor the zoom at the cursor: the point under it stays under it
    const cxr = e.clientX - r.left - r.width / 2;
    const cyr = e.clientY - r.top - r.height / 2;
    v.pan.x = cxr - (cxr - v.pan.x) * factor;
    v.pan.y = cyr - (cyr - v.pan.y) * factor;
    persistView(v);
    drawGraphView(v);
  }, { passive: false });
  v.cv.addEventListener('click', (e) => {
    if (viewMode(v) === 'automaton' && !v.dragMoved && v.autoHits) {
      const r = v.cv.getBoundingClientRect();
      const ux = (e.clientX - r.left - v.rtx) / v.rk;
      const uy = (e.clientY - r.top - v.rty) / v.rk;
      const hit = v.autoHits.find((b) => ux >= b.x - 2 && ux <= b.x + b.w + 2 && uy >= b.y - 2 && uy <= b.y + b.h + 2);
      if (hit) {
        cur.rule = cur.rule === hit.c.name ? '' : hit.c.name;
        if (cur.rule) railChipShow(cur.rule, e.clientX, e.clientY);
        ask();
      }
      return;
    }
    if (viewMode(v) !== 'rails' || v.dragMoved || !v.railHits) return;
    const r = v.cv.getBoundingClientRect();
    const ux = (e.clientX - r.left - v.rtx) / v.rk;
    const uy = (e.clientY - r.top - v.rty) / v.rk;
    const hit = v.railHits.find((b) => ux >= b.x && ux <= b.x + b.w && uy >= b.y && uy <= b.y + b.h);
    if (!hit) return;
    cur.rule = hit.rule;
    railsGoto(v, hit.rule);
    railChipShow(hit.rule, e.clientX, e.clientY);
    ask();
  });
  v.cv.addEventListener('mousemove', (e) => {
    if (viewMode(v) === 'automaton' && v.autoHits) {
      const r = v.cv.getBoundingClientRect();
      const ux = (e.clientX - r.left - v.rtx) / v.rk;
      const uy = (e.clientY - r.top - v.rty) / v.rk;
      const hit = v.autoHits.find((b) => ux >= b.x - 2 && ux <= b.x + b.w + 2 && uy >= b.y - 2 && uy <= b.y + b.h + 2);
      v.cv.style.cursor = hit ? 'pointer' : '';
      const name = hit ? hit.c.name : '';
      if (name !== graphHover) { graphHover = name; ask(); }
      return;
    }
    if (viewMode(v) !== 'rails' || !v.railHits) { v.cv.style.cursor = ''; return; }
    const r = v.cv.getBoundingClientRect();
    const ux = (e.clientX - r.left - v.rtx) / v.rk;
    const uy = (e.clientY - r.top - v.rty) / v.rk;
    const hit = v.railHits.find((b) => ux >= b.x && ux <= b.x + b.w && uy >= b.y && uy <= b.y + b.h);
    v.cv.style.cursor = hit ? 'pointer' : '';
    const rule = hit ? hit.rule : '';
    if (rule !== graphHover) { graphHover = rule; ask(); }
  });
  v.cv.addEventListener('mouseout', () => {
    if (graphHover) { graphHover = ''; ask(); }
  });
  v.chips.addEventListener('mouseover', (e) => {
    const el = e.target.closest('.gchip');
    if (el && el.dataset.name !== graphHover) { graphHover = el.dataset.name; ask(); }
  });
  v.chips.addEventListener('mouseout', () => {
    if (graphHover) { graphHover = ''; ask(); }
  });
  v.chips.addEventListener('click', (e) => {
    const el = e.target.closest('.gchip');
    if (!el) return;
    cur.rule = cur.rule === el.dataset.name ? '' : el.dataset.name;
    if (cur.rule) railChipShow(cur.rule, e.clientX, e.clientY);
    ask();
  });
}

let focusOn = false;

function focusSet() {
  if (!focusOn || !cur.rule) return null;
  const keep = new Set([cur.rule]);
  for (const [a, b] of S.edges) if (b === cur.rule) keep.add(a);
  let frontier = [cur.rule];
  while (frontier.length) {
    const next = [];
    for (const [a, b] of S.edges) {
      if (frontier.includes(a) && !keep.has(b)) { keep.add(b); next.push(b); }
    }
    frontier = next;
  }
  return keep;
}

function persistView(v) {
  if (v.pin) postPolicyDebounced(`pin.${v.pin.id}`, pinPolicyValue(v.pin));
  else postPolicyDebounced('graph.camera',
    `${v.yaw.toFixed(2)} ${v.pitch.toFixed(2)} ${v.zoom.toFixed(2)} ${Math.round(v.pan.x)} ${Math.round(v.pan.y)}`);
}

function pinPolicyValue(p) {
  if (p.kind === 'graph') {
    const v = p.view;
    return `graph ${Math.round(p.x)} ${Math.round(p.y)} ${Math.round(p.w)} ${Math.round(p.h || 440)}`
      + (v ? ` ${v.yaw.toFixed(2)} ${v.pitch.toFixed(2)} ${v.zoom.toFixed(2)} ${Math.round(v.pan.x)} ${Math.round(v.pan.y)}`
           : ' 0.9 0.92 1 0 0')
      + ` ${p.mode || 'depth3d'}`;
  }
  if (p.kind === 'rail') {
    return `rail ${p.rule} ${Math.round(p.x)} ${Math.round(p.y)} ${Math.round(p.w || 520)} ${Math.round(p.h || 300)}`;
  }
  return `span ${p.s} ${p.e} ${p.d} ${p.rule} ${Math.round(p.x)} ${Math.round(p.y)} ${Math.round(p.w || 360)} ${Math.round(p.h || 0)} ${p.gen}`;
}

function graphPin() {
  if (!gNodes) buildGraph();
  const k = pins.length;
  pins.push({
    id: ++pinSeq, kind: 'graph', rule: 'RULE GRAPH',
    x: 300 + (k % 8) * 44, y: 90 + (k % 8) * 44, w: 520,
  });
  renderPins();
}
