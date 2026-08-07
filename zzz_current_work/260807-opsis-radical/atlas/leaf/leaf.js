/* opsis facets — the leaf. Generic and nameless: it draws addressed regions and
   reports gestures. Subjects never cross the seam; addresses do. The document
   plane is REAL text — native selection drives structural co-selection. */

'use strict';

const $ = (id) => document.getElementById(id);
const C = {
  field: '#0b0e14', ink: '#e8e2d6', dim: '#66707f', dimmer: '#3a4250',
  cool: '#6fc3c9', warm: '#e2a65c', violet: '#d98cf5', red: '#e06060',
  green: '#79c99a', closed: '#10282e', active: '#3a2f18', pending: '#2a3140',
};
let LH = 19;
const PAD_TOP = 8;
let docZoom = 1;

let S = null;            // the scene: doc, reader, spans, rules, meta
let M = null;            // measured geometry: charW, gutterW
let cur = { t: 0, playing: false, sel: -1, hover: -1, rule: '', docSel: null, frontier: -1, fstarts: null };
let dirty = false;
let pins = [];      // pinned occurrences and pinned facets — uncapped, by ruling
let speed = 1;      // derivation sweep multiplier ([ and ] halve/double)
let pinSeq = 0;
let pinZ = 30;
let view0 = 0;           // chart viewport (leaf-local)
let chartZoom = 1;       // plain scroll on the chart: zoom the lane window
let lastPost = 0;
let needsDraw = false;

/* ── scene wire: line-oriented text, length-prefixed blocks ── */

function parseScene(text) {
  const scene = { meta: {}, ruledefs: [], ruleNames: [], fieldNames: [], spans: [] };
  let i = 0;
  const nextLine = () => {
    const j = text.indexOf('\n', i);
    const line = text.slice(i, j);
    i = j + 1;
    return line;
  };
  nextLine(); // #META
  for (let line = nextLine(); !line.startsWith('#'); line = nextLine()) {
    const k = line.indexOf(' ');
    scene.meta[line.slice(0, k)] = line.slice(k + 1);
    if (text[i] === '#') break;
  }
  scene.edges = [];
  scene.depths = {};
  for (let guard = 0; guard < 12 && i < text.length; guard++) {
    const head = nextLine().split(' ');
    const tag = head[0], n = parseInt(head[1], 10);
    if (tag === '#READER') { scene.reader = text.slice(i, i + n); i += n + 1; continue; }
    if (tag === '#DOC') { scene.doc = text.slice(i, i + n); i += n + 1; continue; }
    const lines = [];
    for (let k = 0; k < n; k++) lines.push(nextLine());
    if (tag === '#RULEDEFS') {
      for (const ln of lines) {
        const parts = ln.split(' ');
        scene.ruledefs.push({ name: parts.slice(0, -2).join(' '), a: +parts.at(-2), b: +parts.at(-1) });
      }
    } else if (tag === '#RULENAMES') scene.ruleNames = lines;
    else if (tag === '#FIELDNAMES') scene.fieldNames = lines;
    else if (tag === '#SPANS') {
      for (const ln of lines) {
        const p = ln.split(' ');
        scene.spans.push({ s: +p[0], e: +p[1], d: +p[2], r: +p[3], f: +p[4] });
      }
    } else if (tag === '#EDGES') {
      scene.edges = lines.map((ln) => ln.split(' '));
    } else if (tag === '#DEPTHS') {
      for (const ln of lines) {
        const sp = ln.lastIndexOf(' ');
        scene.depths[ln.slice(0, sp)] = +ln.slice(sp + 1);
      }
    }
  }
  scene.lineStarts = starts(scene.doc);
  scene.readerLines = scene.reader.split('\n');
  scene.maxdepth = scene.spans.reduce((m, s) => Math.max(m, s.d), 0);
  scene.byEnd = [...scene.spans.keys()].sort((a, b) => scene.spans[a].e - scene.spans[b].e);
  scene.ruleOf = {};
  scene.ruledefs.forEach((r) => { scene.ruleOf[r.name] = r; });
  return scene;
}

function starts(text) {
  const out = [0];
  for (let i = 0; i < text.length; i++) if (text[i] === '\n') out.push(i + 1);
  return out;
}

/* ── span queries (linear scans: 12k spans is nothing) ── */

const lineOf = (off) => {
  let lo = 0, hi = S.lineStarts.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (S.lineStarts[mid] <= off) lo = mid; else hi = mid - 1; }
  return lo;
};
const deepestAt = (off) => {
  let best = -1;
  S.spans.forEach((s, i) => { if (s.s <= off && off < s.e && (best < 0 || s.d > S.spans[best].d)) best = i; });
  return best;
};
const smallestOver = (lo, hi) => {
  let best = -1;
  S.spans.forEach((s, i) => {
    if (s.s <= lo && hi <= s.e && (best < 0 || s.e - s.s < S.spans[best].e - S.spans[best].s)) best = i;
  });
  return best;
};
const openAt = (t) => S.spans.map((s, i) => i).filter((i) => S.spans[i].s < t && t < S.spans[i].e)
  .sort((a, b) => S.spans[a].d - S.spans[b].d);

/* ── build the two text facets ── */

function buildCode(host, textLines, gutter) {
  host.textContent = '';
  const frag = document.createDocumentFragment();
  textLines.forEach((line, i) => {
    const div = document.createElement('div');
    div.className = 'ln';
    div.dataset.l = i;
    if (gutter) {
      const g = document.createElement('span');
      g.className = 'g';
      g.textContent = i + 1;
      div.appendChild(g);
    }
    const t = document.createElement('span');
    t.className = 't';
    t.textContent = line;
    div.appendChild(t);
    frag.appendChild(div);
  });
  host.appendChild(frag);
}

function measure() {
  const doc = $('docText');
  const cs = getComputedStyle(doc);
  const probe = document.createElement('span');
  probe.textContent = 'M'.repeat(40);
  probe.style.position = 'absolute';
  probe.style.visibility = 'hidden';
  probe.style.whiteSpace = 'pre';
  probe.style.fontFamily = cs.fontFamily;
  probe.style.fontSize = cs.fontSize;
  probe.style.letterSpacing = cs.letterSpacing;
  document.body.appendChild(probe);
  M = { charW: probe.getBoundingClientRect().width / 40, gutterW: doc.offsetLeft };
  probe.remove();
}

function buildGutter(n) {
  const g = $('gutter');
  g.textContent = '';
  const frag = document.createDocumentFragment();
  for (let i = 1; i <= n; i++) {
    const d = document.createElement('div');
    d.textContent = i;
    frag.appendChild(d);
  }
  g.appendChild(frag);
}

function setStale(on) {
  for (const id of ['chart', 'spine', 'grammar']) $(id).classList.toggle('stale', on);
}

function sizeDocCanvases() {
  const wrap = $('docWrap');
  const w = wrap.scrollWidth, h = wrap.scrollHeight;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  for (const cv of [$('under'), $('over')]) {
    cv.width = w * dpr; cv.height = h * dpr;
    cv.style.width = w + 'px'; cv.style.height = h + 'px';
    cv.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

/* ── document plane drawing ── */

function segRects(s, e, l0, l1, fn) {
  for (let line = Math.max(lineOf(s), l0); line <= Math.min(lineOf(Math.max(s, e - 1)), l1); line++) {
    const a = Math.max(s, S.lineStarts[line]);
    const b = Math.min(e, (S.lineStarts[line + 1] ?? S.doc.length + 1) - 1);
    if (b < a) continue;
    const c0 = a - S.lineStarts[line], c1 = b - S.lineStarts[line];
    fn(M.gutterW + c0 * M.charW, PAD_TOP + line * LH, Math.max((c1 - c0) * M.charW, 3), LH);
  }
}

function visibleLines() {
  const sc = $('docScroll');
  const l0 = Math.max(0, Math.floor((sc.scrollTop - PAD_TOP) / LH) - 2);
  const l1 = Math.min(S.lineStarts.length - 1, Math.ceil((sc.scrollTop + sc.clientHeight) / LH) + 2);
  return [l0, l1];
}

function drawUnder() {
  const cx = $('under').getContext('2d');
  cx.clearRect(0, 0, 1e6, 1e6);
  if (dirty) return;
  const [l0, l1] = visibleLines();
  for (const i of openAt(cur.t)) {
    cx.fillStyle = 'rgba(111,195,201,0.045)';
    segRects(S.spans[i].s, S.spans[i].e, l0, l1, (x, y, w, h) => cx.fillRect(x, y, w, h));
  }
  if (markedRule()) {
    cx.strokeStyle = C.violet;
    for (const [i, s] of S.spans.entries()) {
      if (S.ruleNames[s.r] !== markedRule()) continue;
      segRects(s.s, s.e, l0, l1, (x, y, w, h) => cx.strokeRect(x + 0.5, y + 1.5, w - 1, h - 3));
    }
  }
  if (cur.hover >= 0 && cur.hover !== cur.sel) {
    const s = S.spans[cur.hover];
    cx.fillStyle = 'rgba(102,112,127,0.16)';
    segRects(s.s, s.e, l0, l1, (x, y, w, h) => cx.fillRect(x, y, w, h));
  }
  if (cur.sel >= 0) {
    const s = S.spans[cur.sel];
    cx.fillStyle = 'rgba(226,166,92,0.12)';
    cx.strokeStyle = C.warm;
    segRects(s.s, s.e, l0, l1, (x, y, w, h) => { cx.fillRect(x, y, w, h); cx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1); });
  }
}

function frontierMark(cx) {
  if (cur.frontier < 0) return;
  const sts = cur.fstarts || S.lineStarts;
  let lo = 0, hi = sts.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (sts[mid] <= cur.frontier) lo = mid; else hi = mid - 1; }
  const fx = M.gutterW + (cur.frontier - sts[lo]) * M.charW;
  const fy = PAD_TOP + lo * LH;
  cx.fillStyle = C.red;
  cx.shadowColor = C.red; cx.shadowBlur = 8;
  cx.fillRect(fx - 1, fy, 2, LH);
  cx.fillRect(fx - 4, fy + LH - 2, Math.max(M.charW + 8, 12), 2);
  cx.shadowBlur = 0;
}

function drawOver() {
  const cx = $('over').getContext('2d');
  cx.clearRect(0, 0, 1e6, 1e6);
  if (dirty) { frontierMark(cx); return; }
  const wrap = $('docWrap');
  const t = Math.min(cur.t, S.doc.length);
  const line = lineOf(Math.min(Math.floor(t), S.doc.length - 1));
  const x = M.gutterW + (Math.floor(t) - S.lineStarts[line]) * M.charW;
  const y = PAD_TOP + line * LH;
  cx.fillStyle = 'rgba(11,14,20,0.60)';
  cx.fillRect(x, y, wrap.scrollWidth - x, LH);
  if (y + LH < wrap.scrollHeight) cx.fillRect(0, y + LH, wrap.scrollWidth, wrap.scrollHeight - y - LH);
  cx.fillStyle = C.warm;
  cx.shadowColor = C.warm; cx.shadowBlur = 6;
  cx.fillRect(x - 1, y, 2, LH);
  cx.shadowBlur = 0;
  frontierMark(cx);
}

/* ── chart facet: overview density + depth lanes ── */

function drawChart() {
  const cv = $('chartCv');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const cx = cv.getContext('2d');
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  const pad = 10, bandH = 26, N = S.doc.length;
  const ox = (off) => pad + (off / N) * (w - 2 * pad);
  if (!S.cov) {
    const diff = new Int32Array(N + 1);
    S.spans.forEach((s) => { diff[s.s]++; diff[s.e]--; });
    S.cov = new Int32Array(N); let run = 0, top = 1;
    for (let i = 0; i < N; i++) { run += diff[i]; S.cov[i] = run; top = Math.max(top, run); }
    S.covTop = top;
  }
  const shades = ['#0e151d', '#152230', '#1d3143', '#274257'];
  const step = Math.max(1, Math.floor(N / (w - 2 * pad)));
  for (let off = 0; off < N; off += step) {
    let m = 0;
    for (let k = off; k < Math.min(off + step, N); k++) m = Math.max(m, S.cov[k]);
    cx.fillStyle = shades[Math.min(3, Math.floor((m * 4) / (S.covTop + 1)))];
    cx.fillRect(ox(off), 8, Math.max(1, ox(off + step) - ox(off)), bandH);
  }
  // a small document fills the width; a large one gets a 5px-per-char window
  const base = N * 5 < (w - 2 * pad) ? Math.min(12, Math.floor((w - 2 * pad) / Math.max(1, N))) : 5;
  const pitch = Math.max(0.5, base * chartZoom);
  const win = Math.max(8, Math.floor((w - 2 * pad) / pitch));
  view0 = Math.max(0, Math.min(view0, Math.max(0, N - win)));
  if (cur.t < view0 || cur.t > view0 + win * 0.72) {
    view0 = Math.max(0, Math.min(cur.t - win * 0.6, Math.max(0, N - win)));
  }
  cx.strokeStyle = C.warm;
  cx.strokeRect(ox(view0), 5, ox(Math.min(view0 + win, N)) - ox(view0), bandH + 6);
  const lanesY = bandH + 22;
  const laneH = Math.max(6, Math.min(22, Math.floor((h - lanesY - 8) / (S.maxdepth + 1))));
  const sx = (off) => pad + (off - view0) * pitch;
  S.chartHit = { pad, bandH, lanesY, laneH, pitch, win, ox };
  for (const s of S.spans) {
    if (s.e <= view0 || s.s >= view0 + win) continue;
    const x1 = sx(Math.max(s.s, view0)), x2 = sx(Math.min(s.e, view0 + win));
    const y = lanesY + s.d * laneH;
    if (s.e <= cur.t) { cx.fillStyle = C.closed; cx.fillRect(x1, y, x2 - x1, laneH - 2); cx.strokeStyle = C.cool; }
    else if (s.s < cur.t) {
      cx.fillStyle = C.active; cx.fillRect(x1, y, sx(Math.min(cur.t, view0 + win)) - x1, laneH - 2);
      cx.strokeStyle = C.warm;
    } else cx.strokeStyle = C.pending;
    cx.strokeRect(x1 + 0.5, y + 0.5, Math.max(x2 - x1 - 1, 2), laneH - 2);
    const idx = S.spans.indexOf(s);
    if (idx === cur.sel || idx === cur.hover) {
      cx.strokeStyle = idx === cur.sel ? C.warm : C.dim;
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 1);
    }
    if (markedRule() && S.ruleNames[s.r] === markedRule()) {
      cx.strokeStyle = C.violet;
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 1);
    }
  }
  const cxx = sx(Math.min(Math.max(cur.t, view0), view0 + win));
  cx.strokeStyle = C.warm;
  cx.beginPath(); cx.moveTo(cxx, lanesY - 6); cx.lineTo(cxx, h - 4); cx.stroke();
}

/* ── spine facet ── */

let lastSpineKey = '';
function drawSpine() {
  const open = openAt(cur.t);
  const key = open.join(',') + '|' + Math.floor(cur.t);
  if (key === lastSpineKey) return;
  lastSpineKey = key;
  const body = $('spineBody');
  body.textContent = '';
  if (!open.length) body.innerHTML = '<div class="none">nothing open — before the first span, or complete</div>';
  open.forEach((i, k) => {
    const s = S.spans[i];
    const row = document.createElement('div');
    row.className = 'row' + (k === open.length - 1 ? ' deep' : '');
    row.dataset.i = i;
    row.innerHTML = `<span class="d">d${s.d}</span>${S.ruleNames[s.r]} <span class="f">${s.s.toLocaleString()}..${s.e.toLocaleString()}</span>`;
    body.appendChild(row);
  });
  const closedBody = $('closedBody');
  closedBody.textContent = '';
  const done = S.byEnd.filter((i) => S.spans[i].e <= cur.t).slice(-7);
  done.forEach((i) => {
    const s = S.spans[i];
    const snip = S.doc.slice(s.s, s.e).replace(/\n/g, '↵');
    const row = document.createElement('div');
    row.className = 'row' + (cur.t - s.e < 3 ? ' fresh' : '');
    row.dataset.i = i;
    row.innerHTML = `<span class="d">d${s.d}</span>${S.ruleNames[s.r]}  '${snip.length > 22 ? snip.slice(0, 21) + '…' : snip}'`;
    closedBody.appendChild(row);
  });
}

/* ── grammar facet co-selection ── */

function litRules() {
  const selRule = cur.sel >= 0 ? S.ruleNames[S.spans[cur.sel].r] : null;
  const selDef = selRule ? ruleDef(selRule) : null;
  const curDef = cur.rule ? ruleDef(cur.rule) : null;
  const hotDef = hotRule() ? ruleDef(hotRule()) : null;
  document.querySelectorAll('#grammarBody .ln').forEach((ln) => {
    const i = +ln.dataset.l;
    const inDef = (d) => d && d.a <= i && i <= d.b;
    ln.classList.toggle('lit', inDef(selDef) || inDef(curDef));
    ln.classList.toggle('hot', inDef(hotDef));
  });
  const target = selDef || hotDef || curDef;
  if (target) {
    const ln = document.querySelector(`#grammarBody .ln[data-l="${target.a}"]`);
    if (ln) ln.scrollIntoView({ block: 'nearest' });
  }
}

/* ── the frame ── */

function render() {
  needsDraw = false;
  if (dirty) {
    drawUnder(); drawOver();
    $('pos').textContent = `edited — unread · Ctrl+Enter re-reads · Ctrl+S saves (saving compiles) · Esc reverts · gen ${S.meta.generation}`;
    $('readout').textContent = 'the derived facets show the LAST GOOD reading until the text is re-read';
    return;
  }
  followCursor();
  drawUnder(); drawOver(); drawChart(); drawSpine(); litRules(); drawGraph();
  const state = cur.playing ? 'playing' : (cur.t >= S.doc.length ? 'complete' : 'paused');
  const line = lineOf(Math.min(Math.floor(cur.t), S.doc.length - 1)) + 1;
  $('pos').textContent =
    `char ${Math.floor(Math.min(cur.t, S.doc.length)).toLocaleString()} / ${S.doc.length.toLocaleString()}`
    + ` · line ${line.toLocaleString()} / ${S.lineStarts.length.toLocaleString()} · ${state}`
    + (speed !== 1 ? ` · speed ${speedWord()}` : '') + ` · gen ${S.meta.generation}`;
  $('tb-play').textContent = cur.playing ? '⏸' : '▶';
  $('tb-speed').textContent = speedWord();
  const focus = cur.sel >= 0 ? cur.sel : cur.hover;
  $('readout').textContent = focus < 0 ? (cur.rule ? `rule ${cur.rule} — its spans outlined violet` : '') : spanWords(focus);
  if (performance.now() - lastPost > 300) {
    lastPost = performance.now();
    fetch('/cursor', { method: 'POST', body: `t ${cur.t.toFixed(1)} sel ${cur.sel}` }).catch(() => {});
  }
}

/* ── the 3D rule graph — z is derivation distance, the earned axis ── */

let graphOn = false;
let gNodes = null;
let graphHover = '';
let gViews = [];  // [0] is the facet view; others live inside pinned windows

function makeGraphView(wrap, cv, chips) {
  return { wrap, cv, chips, yaw: 0.42, pitch: 0.92, zoom: 1 };
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
    const R = k === 1 ? 0 : 46 + Math.min(230, k * 15);
    names.forEach((n, i) => {
      const a = (i / k) * Math.PI * 2 + lvl * 0.7;
      gNodes.set(n, { x: Math.cos(a) * R, y: Math.sin(a) * R * 0.78, z: -lvl * 150 });
    });
  }
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
  if (!gNodes) return;
  for (const v of gViews) {
    if (!document.contains(v.wrap) || v.wrap.closest('[hidden]')) continue;
    drawGraphView(v);
  }
}

function drawGraphView(v, smooth = false) {
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
  for (const [name, p] of gNodes) proj.set(name, gProject(v, p, w, h));
  // auto-fit: fill the facet whatever the grammar's size or the orbit's angle
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  for (const P of proj.values()) {
    x0 = Math.min(x0, P.x); x1 = Math.max(x1, P.x);
    y0 = Math.min(y0, P.y); y1 = Math.max(y1, P.y);
  }
  const tk = Math.min((w * 0.84) / Math.max(40, x1 - x0), (h * 0.78) / Math.max(40, y1 - y0), 2.4) * v.zoom;
  const tmx = (x0 + x1) / 2, tmy = (y0 + y1) / 2;
  if (!v.fit || !smooth) v.fit = { k: tk, mx: tmx, my: tmy };
  else {
    v.fit.k += (tk - v.fit.k) * 0.22;
    v.fit.mx += (tmx - v.fit.mx) * 0.22;
    v.fit.my += (tmy - v.fit.my) * 0.22;
  }
  const { k, mx, my } = v.fit;
  for (const P of proj.values()) {
    P.x = w / 2 + (P.x - mx) * k;
    P.y = h / 2 + (P.y - my) * k;
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
    cx.moveTo(A.x, A.y);
    cx.lineTo(B.x, B.y);
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
    el.classList.toggle('near', P.s > 0.85);
    el.classList.toggle('start', el.dataset.name === start);
    el.classList.toggle('marked', el.dataset.name === cur.rule);
    el.classList.toggle('hot', el.dataset.name === hot);
    el.classList.toggle('faded', keep !== null && !keep.has(el.dataset.name));
  }
}

function setGraph(on) {
  graphOn = on;
  $('grammarScroll').hidden = on;
  $('graphWrap').hidden = !on;
  $('gmode').textContent = on ? 'text' : 'graph';
  $('gpop').hidden = !on;
  $('gfocus').hidden = !on;
  if (on && !gNodes) buildGraph();
  if (on) drawGraph();
}

function wireGraphView(v) {
  let drag = null;
  v.wrap.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.gchip')) return;
    drag = { x: e.clientX, y: e.clientY };
    e.preventDefault();
  });
  window.addEventListener('pointermove', (e) => {
    if (!drag) return;
    v.yaw += (e.clientX - drag.x) * 0.006;
    v.pitch = Math.max(-1.4, Math.min(1.4, v.pitch + (e.clientY - drag.y) * 0.005));
    drag = { x: e.clientX, y: e.clientY };
    drawGraphView(v, true);
  });
  window.addEventListener('pointerup', () => { drag = null; });
  v.wrap.addEventListener('wheel', (e) => {
    e.preventDefault();
    v.zoom = Math.max(0.35, Math.min(5, v.zoom * Math.pow(1.0016, -e.deltaY)));
    drawGraphView(v);
  }, { passive: false });
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

function graphPin() {
  if (!gNodes) buildGraph();
  const k = pins.length;
  pins.push({
    id: ++pinSeq, kind: 'graph', rule: 'RULE GRAPH',
    x: 300 + (k % 8) * 44, y: 90 + (k % 8) * 44, w: 520,
  });
  renderPins();
}

let spineZoom = 1;

function wireSpineZoom() {
  // text fields zoom with Ctrl+scroll, like an editor
  $('spine').addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    spineZoom = Math.max(0.6, Math.min(2.4, spineZoom * Math.pow(1.0016, -e.deltaY)));
    for (const id of ['spineBody', 'closedBody']) {
      $(id).style.fontSize = (11.5 * spineZoom).toFixed(1) + 'px';
    }
  }, { passive: false });
}

function applyDocZoom() {
  LH = Math.round(19 * docZoom);
  document.documentElement.style.setProperty('--fs', (12.5 * docZoom).toFixed(1) + 'px');
  document.documentElement.style.setProperty('--lh', LH + 'px');
  measure();
  sizeDocCanvases();
}

function wireTextZoom() {
  for (const id of ['docScroll', 'grammarScroll']) {
    $(id).addEventListener('wheel', (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      docZoom = Math.max(0.6, Math.min(2.2, docZoom * Math.pow(1.0016, -e.deltaY)));
      applyDocZoom();
      ask();
    }, { passive: false });
  }
}

function wireChartZoom() {
  $('chartCv').addEventListener('wheel', (e) => {
    e.preventDefault();
    chartZoom = Math.max(0.25, Math.min(8, chartZoom * Math.pow(1.0016, -e.deltaY)));
    ask();
  }, { passive: false });
}

function wireGraph() {
  $('gmode').addEventListener('click', () => setGraph(!graphOn));
  $('gpop').addEventListener('click', graphPin);
  $('gfocus').addEventListener('click', () => {
    focusOn = !focusOn;
    $('gfocus').classList.toggle('on', focusOn);
    drawGraph();
  });
  const facetView = makeGraphView($('graphWrap'), $('graphCv'), $('graphChips'));
  gViews.push(facetView);
  wireGraphView(facetView);
}

/* ── pinned windows — uncapped, by ruling: let the people have fun ── */

let pinMeasure = null;

function addPin(spanIdx) {
  if (spanIdx < 0) {
    const banner = $('banner');
    banner.hidden = false;
    banner.className = 'refuse';
    banner.textContent = 'nothing to pin — select text, or hover an occurrence first';
    return;
  }
  const s = S.spans[spanIdx];
  const k = pins.length;
  pins.push({
    id: ++pinSeq, gen: S.meta.generation, s: s.s, e: s.e, d: s.d,
    rule: S.ruleNames[s.r], field: S.fieldNames[s.f] || '',
    snip: S.doc.slice(s.s, Math.min(s.e, s.s + 400)),
    x: 240 + (k % 8) * 44 + Math.floor(k / 8) * 12,
    y: 110 + (k % 8) * 44,
    w: 0,
  });
  renderPins();
}

function pinWidth(p, el) {
  // wide enough that the pinned text does not wrap, viewport permitting
  if (!pinMeasure) pinMeasure = document.createElement('canvas').getContext('2d');
  pinMeasure.font = getComputedStyle(el.querySelector('.snip')).font;
  let w = 0;
  for (const line of p.snip.split('\n')) w = Math.max(w, pinMeasure.measureText(line).width);
  return Math.max(280, Math.min(Math.ceil(w) + 28, Math.floor(window.innerWidth * 0.62)));
}

function pinSpanIdx(p) {
  if (p.gen !== S.meta.generation) return -1;
  return S.spans.findIndex((s) => s.s === p.s && s.e === p.e && s.d === p.d);
}

function ruleDefText(rule) {
  const def = ruleDef(rule);
  if (!def) return '';
  return S.readerLines.slice(def.a, Math.min(def.b + 1, def.a + 3)).join('\n');
}

function buildPin(p, layer) {
  const el = document.createElement('div');
  el.className = 'pin' + (p.kind === 'graph' ? ' graph' : '');
  el.dataset.id = p.id;
  el.style.left = p.x + 'px';
  el.style.top = p.y + 'px';
  el.style.zIndex = ++pinZ;
  if (p.kind === 'graph') {
    el.style.width = p.w + 'px';
    el.style.height = '440px';
    el.innerHTML =
      `<header><span>RULE GRAPH</span><span class="addr">z = derivation distance · drag orbits · wheel zooms</span>`
      + `<span class="stalemark"></span><button class="x" title="close">×</button></header>`
      + `<div class="body gbody"><div class="gwrap"><canvas></canvas><div class="gchips"></div></div></div>`;
    layer.appendChild(el);
    const wrap = el.querySelector('.gwrap');
    const v = makeGraphView(wrap, el.querySelector('canvas'), el.querySelector('.gchips'));
    v.yaw = 0.9;
    gViews.push(v);
    if (gNodes) buildChipsInto(v.chips);
    wireGraphView(v);
    new ResizeObserver(() => drawGraphView(v)).observe(wrap);
    drawGraphView(v);
    return el;
  }
  el.innerHTML =
    `<header><span>${p.rule}</span><span class="addr">${p.s.toLocaleString()}..${p.e.toLocaleString()} · d${p.d}</span>`
    + `<span class="stalemark"></span>`
    + `<button class="x" title="close">×</button></header>`
    + `<div class="body"><div class="snip"></div>`
    + `<div class="facts"></div>`
    + `<div class="def"></div></div>`;
  el.querySelector('.snip').textContent = p.snip + (p.e - p.s > 400 ? ' …' : '');
  layer.appendChild(el);
  if (!p.w) p.w = pinWidth(p, el);
  el.style.width = p.w + 'px';
  return el;
}

function renderPins() {
  // reconcile, never rebuild: a hand-resized window keeps its size and scroll
  const layer = $('pinlayer');
  const seen = new Set();
  for (const p of pins) {
    seen.add(String(p.id));
    let el = layer.querySelector(`.pin[data-id="${p.id}"]`);
    if (!el) el = buildPin(p, layer);
    if (p.kind === 'graph') continue;
    const stale = p.gen !== S.meta.generation;
    el.classList.toggle('stale', stale);
    el.querySelector('.stalemark').textContent = stale ? `gen ${p.gen} — stale` : '';
    el.querySelector('.facts').textContent =
      (p.field ? 'field ' + p.field + ' · ' : '') + `pinned against gen ${p.gen}`
      + (stale ? ' · the document has moved on — re-pin or close' : '');
    el.querySelector('.def').textContent = stale ? '' : ruleDefText(p.rule);
  }
  for (const el of [...layer.children]) {
    if (!seen.has(el.dataset.id)) {
      gViews = gViews.filter((v) => !el.contains(v.wrap));
      el.remove();
    }
  }
  $('pincount').textContent = pins.length ? `pinned ${pins.length}` : '';
}

let chipSticky = false;

function chipAt(off, sticky = false) {
  chipSticky = sticky;
  // position the chip from glyph geometry — one path for selection and ?sel
  const chip = $('pinchip');
  const wrap = $('docWrap').getBoundingClientRect();
  const line = lineOf(Math.min(off, S.doc.length - 1));
  const col = off - S.lineStarts[line];
  const x = wrap.left + M.gutterW + col * M.charW;
  const y = wrap.top + PAD_TOP + line * LH;
  chip.style.left = Math.max(8, Math.min(x + 6, window.innerWidth - 90)) + 'px';
  chip.style.top = Math.max(8, Math.min(y - 30, window.innerHeight - 42)) + 'px';
  chip.hidden = false;
}

function hideChip(force = false) {
  if (chipSticky && !force) return;
  $('pinchip').hidden = true;
}

function wireChip() {
  const chip = $('pinchip');
  chip.addEventListener('pointerdown', (e) => e.preventDefault());  // keep the selection alive
  chip.addEventListener('click', () => {
    addPin(cur.sel);
    chipSticky = false;
    hideChip(true);
  });
  $('docScroll').addEventListener('scroll', () => hideChip());
}

function wirePins() {
  const layer = $('pinlayer');
  let drag = null;
  layer.addEventListener('pointerdown', (e) => {
    const el = e.target.closest('.pin');
    if (!el) return;
    el.style.zIndex = ++pinZ;
    if (e.target.closest('.x')) {
      pins = pins.filter((p) => p.id !== +el.dataset.id);
      renderPins();
      return;
    }
    if (e.target.closest('header')) {
      const p = pins.find((q) => q.id === +el.dataset.id);
      drag = { p, el, dx: e.clientX - p.x, dy: e.clientY - p.y };
      e.preventDefault();
    }
  });
  window.addEventListener('pointermove', (e) => {
    if (!drag) return;
    drag.p.x = Math.max(0, e.clientX - drag.dx);
    drag.p.y = Math.max(0, e.clientY - drag.dy);
    drag.el.style.left = drag.p.x + 'px';
    drag.el.style.top = drag.p.y + 'px';
  });
  window.addEventListener('pointerup', () => { drag = null; });
  layer.addEventListener('mousemove', (e) => {
    const el = e.target.closest('.pin');
    const p = el && pins.find((q) => q.id === +el.dataset.id);
    const idx = p ? pinSpanIdx(p) : -1;
    if (idx !== cur.hover) { cur.hover = idx; ask(); }
  });
  layer.addEventListener('mouseleave', () => { cur.hover = -1; ask(); });
  layer.addEventListener('click', (e) => {
    const el = e.target.closest('.pin');
    if (!el || e.target.closest('.x') || e.target.closest('header')) return;
    const p = pins.find((q) => q.id === +el.dataset.id);
    const idx = p ? pinSpanIdx(p) : -1;
    if (idx >= 0) { cur.sel = idx; ask(); }
  });
}

function spanWords(i) {
  const s = S.spans[i];
  const f = S.fieldNames[s.f];
  return `${S.ruleNames[s.r]}${f ? ' · field ' + f : ''} · ${s.s.toLocaleString()}..${s.e.toLocaleString()} · d${s.d}`
    + (cur.docSel ? ' · E retypes the selection' : '');
}

function ask() { if (!needsDraw) { needsDraw = true; requestAnimationFrame(render); } }

let followT = -1;
function followCursor() {
  if (dirty) return;
  if (!cur.playing && followT === cur.t) return;
  followT = cur.t;
  if (!cur.playing && !cur.follow) return;
  cur.follow = false;
  const sc = $('docScroll');
  const y = PAD_TOP + lineOf(Math.min(Math.floor(cur.t), S.doc.length - 1)) * LH;
  if (y < sc.scrollTop + 40 || y > sc.scrollTop + sc.clientHeight - 60) {
    sc.scrollTop = Math.max(0, y - sc.clientHeight * 0.4);
  }
}

/* ── time ── */

let lastTick = 0;
function tick(now) {
  if (!cur.playing) return;
  const dt = lastTick ? (now - lastTick) / 1000 : 0;
  lastTick = now;
  cur.t = Math.min(cur.t + (S.doc.length / 22) * speed * dt, S.doc.length);
  if (cur.t >= S.doc.length) cur.playing = false;
  render();
  if (cur.playing) requestAnimationFrame(tick);
}
function play() {
  if (cur.t >= S.doc.length) cur.t = 0;
  cur.playing = true; lastTick = 0;
  requestAnimationFrame(tick);
}

/* ── gestures ── */

function speedWord() {
  return speed >= 1 ? `×${speed}` : `×1/${Math.round(1 / speed)}`;
}

function wireTransport() {
  $('tb-slow').addEventListener('click', () => { speed = Math.max(1 / 512, speed / 2); ask(); });
  $('tb-fast').addEventListener('click', () => { speed = Math.min(16, speed * 2); ask(); });
  $('tb-play').addEventListener('click', () => {
    cur.playing ? (cur.playing = false, ask()) : play();
  });
  $('tb-back').addEventListener('click', () => {
    cur.playing = false;
    cur.t = Math.max(0, Math.floor(cur.t) - 1);
    cur.follow = true;
    ask();
  });
  $('tb-step').addEventListener('click', () => {
    cur.playing = false;
    cur.t = Math.min(S.doc.length, Math.floor(cur.t) + 1);
    cur.follow = true;
    ask();
  });
}

function wire() {
  const doc = $('docText');
  doc.addEventListener('mousemove', (e) => {
    if (dirty) return;
    const off = offsetAt(e);
    const hover = off < 0 ? -1 : deepestAt(off);
    if (hover !== cur.hover) { cur.hover = hover; ask(); }
  });
  doc.addEventListener('mouseleave', () => { cur.hover = -1; ask(); });
  doc.addEventListener('input', () => {
    if (!dirty) {
      dirty = true;
      setStale(true);
      cur.playing = false; cur.sel = -1; cur.hover = -1; cur.frontier = -1; cur.fstarts = null;
      $('banner').hidden = true;
    }
    ask();
  });
  $('gutter').addEventListener('click', (e) => {
    if (dirty) return;
    const rect = $('gutter').getBoundingClientRect();
    const line = Math.floor((e.clientY - rect.top - PAD_TOP) / LH);
    if (line >= 0 && line < S.lineStarts.length) { cur.playing = false; cur.t = S.lineStarts[line]; ask(); }
  });
  $('docScroll').addEventListener('scroll', ask);
  document.addEventListener('selectionchange', readSelection);
  $('grammarBody').addEventListener('click', (e) => {
    const ln = e.target.closest('.ln');
    if (!ln) return;
    const i = +ln.dataset.l;
    const def = S.ruledefs.find((r) => r.a <= i && i <= r.b);
    cur.rule = def && cur.rule !== def.name ? def.name : '';
    ask();
  });
  const chart = $('chartCv');
  let dragging = false;
  const scrub = (e) => {
    const r = chart.getBoundingClientRect();
    const { pad, bandH, lanesY, laneH, pitch, win } = S.chartHit;
    const x = e.clientX - r.left, y = e.clientY - r.top;
    cur.playing = false;
    if (y < lanesY) cur.t = Math.max(0, Math.min((x - pad) / (r.width - 2 * pad), 1)) * S.doc.length;
    else cur.t = Math.max(0, Math.min(view0 + (x - pad) / pitch, S.doc.length));
    cur.follow = true;  // the overview is also the document's minimap
    ask();
  };
  chart.addEventListener('mousedown', (e) => { dragging = true; scrub(e); });
  window.addEventListener('mouseup', () => { dragging = false; });
  chart.addEventListener('mousemove', (e) => {
    if (dragging) { scrub(e); return; }
    const r = chart.getBoundingClientRect();
    const { pad, lanesY, laneH, pitch, win } = S.chartHit;
    const y = e.clientY - r.top;
    let hover = -1;
    if (y >= lanesY) {
      const d = Math.floor((y - lanesY) / laneH);
      const off = view0 + (e.clientX - r.left - pad) / pitch;
      S.spans.forEach((s, i) => { if (s.d === d && s.s <= off && off < s.e) hover = i; });
    }
    if (hover !== cur.hover) { cur.hover = hover; ask(); }
  });
  for (const host of [$('spineBody'), $('closedBody')]) {
    host.addEventListener('click', (e) => {
      const row = e.target.closest('.row');
      if (row) { cur.sel = +row.dataset.i; lastSpineKey = ''; ask(); }
    });
    host.addEventListener('mousemove', (e) => {
      const row = e.target.closest('.row');
      const h = row ? +row.dataset.i : -1;
      if (h !== cur.hover) { cur.hover = h; ask(); }
    });
  }
  window.addEventListener('resize', ask);
  window.addEventListener('keydown', onKey);
}

function offsetAt(e) {
  const rect = $('docText').getBoundingClientRect();
  const line = Math.floor((e.clientY - rect.top - PAD_TOP) / LH);
  if (line < 0 || line >= S.lineStarts.length) return -1;
  const col = Math.max(0, Math.round((e.clientX - rect.left) / M.charW));
  const len = (S.lineStarts[line + 1] ?? S.doc.length + 1) - 1 - S.lineStarts[line];
  return S.lineStarts[line] + Math.min(col, len);
}

function readSelection() {
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) {
    cur.docSel = null;
    if (document.activeElement !== $('pinchip')) hideChip();
    return;
  }
  if (dirty) return;
  const within = (node) => $('docText').contains(node.nodeType === 3 ? node.parentNode : node);
  if (!within(sel.anchorNode) || !within(sel.focusNode)) return;
  const offOf = (node, k) => {
    const r = document.createRange();
    r.setStart($('docText'), 0);
    r.setEnd(node, k);
    return r.toString().length;
  };
  const a = offOf(sel.anchorNode, sel.anchorOffset), b = offOf(sel.focusNode, sel.focusOffset);
  cur.docSel = { lo: Math.min(a, b), hi: Math.max(a, b) };
  cur.sel = smallestOver(cur.docSel.lo, cur.docSel.hi);
  if (cur.sel >= 0) chipAt(cur.docSel.hi);
  else hideChip();
  ask();
}

function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) { e.preventDefault(); commitDoc(true); return; }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); commitDoc(false); return; }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P')) {
    e.preventDefault();
    addPin(cur.sel >= 0 ? cur.sel : cur.hover);
    return;
  }
  if (e.key === 'Escape') { e.preventDefault(); revertOrClear(); return; }
  if (document.activeElement === $('docText')) return;
  if (e.key === 'p' || e.key === 'P') { addPin(cur.sel >= 0 ? cur.sel : cur.hover); return; }
  if (e.key === 'g' || e.key === 'G') { setGraph(!graphOn); return; }
  if (e.key === '[') { speed = Math.max(1 / 512, speed / 2); ask(); return; }
  if (e.key === ']') { speed = Math.min(16, speed * 2); ask(); return; }
  if (e.key === ' ') { e.preventDefault(); cur.playing ? (cur.playing = false, ask()) : play(); }
  else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    cur.playing = false;
    cur.t = Math.max(0, Math.min(Math.floor(cur.t) + (e.key === 'ArrowRight' ? 1 : -1), S.doc.length));
    ask();
  }
}

async function commitDoc(persist) {
  if (!dirty && !persist) return;
  await applyEdit(0, S.doc.length, $('docText').textContent, persist);
}

function revertOrClear() {
  $('banner').hidden = true;
  if (dirty) {
    $('docText').textContent = S.doc;
    buildGutter(S.lineStarts.length);
    sizeDocCanvases();
    dirty = false;
    setStale(false);
  }
  cur.sel = -1; cur.rule = ''; cur.frontier = -1; cur.fstarts = null;
  ask();
}

async function applyEdit(lo, hi, value, persist) {
  const candidate = S.doc.slice(0, lo) + value + S.doc.slice(hi);
  const url = persist ? '/save' : '/edit';
  const resp = await (await fetch(url, { method: 'POST', body: `${lo} ${hi}\n${value}` })).text();
  const banner = $('banner');
  banner.hidden = false;
  const [head] = resp.split('\n', 1);
  if (head.startsWith('ok')) {
    banner.className = 'ok';
    dirty = false;
    setStale(false);
    cur.frontier = -1; cur.fstarts = null;
    await boot(true);
    const parts = head.split(' ');
    let outcome = `re-read in ${parts[1]}s; every facet re-derived from the text`;
    if (parts[2] === 'saved') outcome += ' · saved to its file';
    if (parts[2] === 'held') outcome += ` · save held: ${parts.slice(3).join(' ')}`;
    banner.textContent = `generation ${S.meta.generation} — ${outcome}`;
    renderPins();  // pins from an older generation mark themselves stale
    return;
  }
  banner.className = 'refuse';
  const words = resp.slice(head.length + 1);
  const pos = parseInt(head.split(' ')[1], 10);
  cur.frontier = Number.isFinite(pos) ? pos : -1;
  cur.fstarts = starts(candidate);
  if ($('docText').textContent !== candidate) $('docText').textContent = candidate;
  dirty = true;
  setStale(true);
  buildGutter(cur.fstarts.length);
  sizeDocCanvases();
  cur.playing = false;
  banner.textContent = cur.frontier >= 0
    ? `${words} — frontier at char ${cur.frontier.toLocaleString()}; fix the text — Ctrl+Enter re-reads, Ctrl+S saves · Esc reverts`
    : `${words} — frontier unmeasured on this route; fix the text — Ctrl+Enter re-reads, Ctrl+S saves · Esc reverts`;
  if (cur.frontier >= 0) {
    let lo2 = 0, hi2 = cur.fstarts.length - 1;
    while (lo2 < hi2) { const mid = (lo2 + hi2 + 1) >> 1; if (cur.fstarts[mid] <= cur.frontier) lo2 = mid; else hi2 = mid - 1; }
    $('docScroll').scrollTop = Math.max(0, PAD_TOP + lo2 * LH - $('docScroll').clientHeight * 0.4);
  }
  ask();
}

/* ── boot ── */

async function boot(keep) {
  const text = await (await fetch('/scene')).text();
  const t0 = keep ? Math.min(cur.t, 1e12) : 0;
  S = parseScene(text);
  cur.sel = -1; cur.hover = -1; cur.docSel = null;
  $('docText').textContent = S.doc;
  buildGutter(S.lineStarts.length);
  buildCode($('grammarBody'), S.readerLines, false);
  measure();
  view0 = 0;
  sizeDocCanvases();
  gNodes = null;
  if (graphOn) buildGraph();
  $('sub').textContent =
    `${S.meta.reader} read ${S.doc.length.toLocaleString()} chars in ${S.meta.seconds}s · `
    + `${S.spans.length.toLocaleString()} spans · depth ${S.maxdepth}`
    + (S.meta.resolver === '1' ? ' · ambiguity settled by a supplied first-derivation resolver' : '');
  $('verdict').innerHTML = S.meta.faithful === '1'
    ? 'model.to_text() == document <span class="holds">— holds</span>'
    : 'model.to_text() == document <span class="fails">— FAILS</span>';
  cur.t = Math.min(t0, S.doc.length);
  lastSpineKey = '';
  ask();
  return S;
}

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
  await boot(false);
  wire();
  wirePins();
  wireChip();
  wireGraph();
  wireTransport();
  wireSpineZoom();
  wireTextZoom();
  wireChartZoom();
  pollRoutes();
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
  if (q.has('focus')) { focusOn = true; $('gfocus').classList.add('on'); drawGraph(); }
  if ([...q.keys()].length === 0) setTimeout(play, 600);  // deterministic states do not animate
})();
