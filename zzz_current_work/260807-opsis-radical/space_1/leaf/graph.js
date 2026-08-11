/* The rule graph — three views of one relation: depth-3d, flat, arcs.
   Carved out of leaf.js because it is one surface with its own state
   (gNodes, gFlat, gArc, gTune) and its own failure modes: it ran off
   the facet, and its crowded levels collided. Both are fixed here, in
   the file that owns them, rather than patched from a distance. */

/* ── the 3D rule graph — z is derivation distance, the earned axis ── */

let graphOn = false;
let gNodes = null;
let graphHover = '';
let gViews = [];  // [0] is the facet view; others live inside pinned windows
let gFlat = new Map();
let gArc = new Map();
let gArcIndex = new Map();

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

function buildGraph() {
  const maxd = Math.max(0, ...Object.values(S.depths).filter((d) => d >= 0));
  const levels = new Map();
  const names = Object.keys(S.depths).length ? Object.keys(S.depths) : S.ruledefs.map((r) => r.name);
  for (const name of names) {
    const d = S.depths[name] ?? -1;
    const lvl = d < 0 ? maxd + 1 : d;
    if (!levels.has(lvl)) levels.set(lvl, []);
    levels.get(lvl).push(name);
  }
  gNodes = new Map();
  for (const [lvl, names] of levels) {
    const k = names.length;
    const R = (k === 1 ? 0 : 46 + Math.min(230, k * 15)) * gTune.ringscale;
    names.forEach((n, i) => {
      const a = (i / k) * Math.PI * 2 + lvl * 0.7;
      gNodes.set(n, {
        x: Math.cos(a) * R,
        y: Math.sin(a) * R * gTune.flatten,
        z: -lvl * gTune.levelstep,
      });
    });
  }
  gFlat = new Map();
  // A crowded level used to run taller than the facet, so the auto-fit shrank
  // the whole graph until the labels sat on top of each other. Wrapping a
  // level into sub-columns keeps every level within one screen height, which
  // means the fit never has to crush the type to make room.
  // Placement has to know how wide a LABEL is, or the columns land closer
  // together than the names they carry and the graph collides with itself.
  // A name is drawn in the mono face at ~6.2px per character; a sub-column
  // is therefore as wide as its widest name, never a fraction of levelstep.
  const TALL = 9;
  const WIDE = 6.2;
  let shove = 0;
  for (const [lvl, list] of [...levels].sort((a, b) => a[0] - b[0])) {
    const cols = Math.ceil(list.length / TALL);
    const per = Math.ceil(list.length / cols);
    const widest = [];
    for (let c = 0; c < cols; c++) {
      const slice = list.slice(c * per, (c + 1) * per);
      widest.push(Math.max(40, ...slice.map((n) => n.length * WIDE)) + 26);
    }
    list.forEach((n, i) => {
      const col = Math.floor(i / per);
      const row = i % per;
      const tall = Math.min(per, list.length - col * per);
      const into = widest.slice(0, col).reduce((a, b) => a + b, 0);
      gFlat.set(n, {
        x: shove + into,
        y: (row - tall / 2) * 26 * gTune.ringscale + (lvl % 2) * 9,
      });
    });
    shove += widest.reduce((a, b) => a + b, 0) + gTune.levelstep * 0.35;
  }
  railsLayout = null;
  gArc = new Map();
  gArcIndex = new Map();
  const order = S.ruledefs.map((r) => r.name).filter((n) => names.includes(n));
  for (const n of names) if (!order.includes(n)) order.push(n);
  order.forEach((n, i) => {
    gArcIndex.set(n, i);
    gArc.set(n, { x: i * (gTune.levelstep / 6), y: 0 });
  });
  for (const v of gViews) buildChipsInto(v.chips);
}

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

function gProject(v, p, w, h) {
  const cy = Math.cos(v.yaw), sy = Math.sin(v.yaw);
  const x = p.x * cy + p.z * sy;
  let z = -p.x * sy + p.z * cy;
  const cp = Math.cos(v.pitch), sp = Math.sin(v.pitch);
  const y = p.y * cp - z * sp;
  z = p.y * sp + z * cp;
  const f = 780;
  const s = f / Math.max(220, f - z + 420);  // near-plane clamp: no pole, no mirror
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
    for (const [name, p] of gNodes) proj.set(name, gProject(v, p, w, h));
  } else {
    const src = mode === 'flat' ? gFlat : gArc;
    for (const [name, q] of src) proj.set(name, { x: q.x, y: q.y, s: 1 });
  }
  // auto-fit: fill the facet whatever the grammar's size or the orbit's angle
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  for (const P of proj.values()) {
    x0 = Math.min(x0, P.x); x1 = Math.max(x1, P.x);
    y0 = Math.min(y0, P.y); y1 = Math.max(y1, P.y);
  }
  let fitk = Math.min((w * 0.84) / Math.max(40, x1 - x0), (h * 0.78) / Math.max(40, y1 - y0), 2.4);
  // the floor keeps a SMALL graph readable; it must never forbid a large one
  // from shrinking, which is how 32 rules ran off the side of the facet
  if (mode !== 'depth3d' && fitk > 0.8) fitk = Math.max(fitk, 0.8);
  const tk = fitk * v.zoom;
  const tmx = (x0 + x1) / 2, tmy = (y0 + y1) / 2;
  if (!v.fit || !smooth) v.fit = { k: tk, mx: tmx, my: tmy };
  else {
    v.fit.k += (tk - v.fit.k) * 0.22;
    v.fit.mx += (tmx - v.fit.mx) * 0.22;
    v.fit.my += (tmy - v.fit.my) * 0.22;
  }
  const { k, mx, my } = v.fit;
  if (mode !== 'depth3d' && !v.touched) {
    v.pan.x = 70 - w / 2 - (x0 - mx) * k;  // untouched camera frames the start rule's edge
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
    cx.strokeStyle = touched
      ? 'rgba(217,140,245,0.75)'
      : `rgba(111,195,201,${(0.06 + 0.22 * Math.min(A.s, B.s)).toFixed(3)})`;
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
    el.classList.toggle('faded', keep !== null && !keep.has(el.dataset.name));
  }
}

function setGraph(on, fromPolicy = false) {
  graphOn = on;
  if (!fromPolicy) postPolicy('reader.mode', on ? 'graph' : 'text');
  $('grammarScroll').hidden = on;
  $('graphWrap').hidden = !on;
  $('gmode').textContent = on ? 'text' : 'graph';
  $('gpop').hidden = !on;
  $('gfocus').hidden = !on;
  $('gview').hidden = !on;
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

