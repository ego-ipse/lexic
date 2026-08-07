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
const LH = 19, PAD_TOP = 8;

let S = null;            // the scene: doc, reader, spans, rules, meta
let M = null;            // measured geometry: charW, gutterW
let cur = { t: 0, playing: false, sel: -1, hover: -1, rule: '', docSel: null, frontier: -1, fstarts: null };
let dirty = false;
let pins = [];      // the ruled exception: pinned occurrences, cap 3
let pinSeq = 0;
let pinZ = 30;
let view0 = 0;           // chart viewport (leaf-local)
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
  const counts = {};
  for (let guard = 0; guard < 6 && i < text.length; guard++) {
    const head = nextLine().split(' ');
    const tag = head[0], n = parseInt(head[1], 10);
    if (tag === '#RULEDEFS') {
      for (let k = 0; k < n; k++) {
        const [name, a, b] = nextLine().split(' ');
        scene.ruledefs.push({ name, a: +a, b: +b });
      }
    } else if (tag === '#RULENAMES') {
      for (let k = 0; k < n; k++) scene.ruleNames.push(nextLine());
    } else if (tag === '#FIELDNAMES') {
      for (let k = 0; k < n; k++) scene.fieldNames.push(nextLine());
    } else if (tag === '#SPANS') {
      for (let k = 0; k < n; k++) {
        const p = nextLine().split(' ');
        scene.spans.push({ s: +p[0], e: +p[1], d: +p[2], r: +p[3], f: +p[4] });
      }
    } else if (tag === '#READER') {
      scene.reader = text.slice(i, i + n); i += n + 1;
    } else if (tag === '#DOC') {
      scene.doc = text.slice(i, i + n); i += n + 1;
    }
    counts[tag] = n;
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
  if (cur.rule) {
    cx.strokeStyle = C.violet;
    for (const [i, s] of S.spans.entries()) {
      if (S.ruleNames[s.r] !== cur.rule) continue;
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
  const pitch = N * 5 < (w - 2 * pad) ? Math.min(12, Math.floor((w - 2 * pad) / Math.max(1, N))) : 5;
  const win = Math.floor((w - 2 * pad) / pitch);
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
    if (cur.rule && S.ruleNames[s.r] === cur.rule) {
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
  const hotRule = cur.hover >= 0 ? S.ruleNames[S.spans[cur.hover].r] : null;
  document.querySelectorAll('#grammarBody .ln').forEach((ln) => {
    const i = +ln.dataset.l;
    const inRule = (name) => name && S.ruleOf[name] && S.ruleOf[name].a <= i && i <= S.ruleOf[name].b;
    ln.classList.toggle('lit', inRule(selRule) || inRule(cur.rule));
    ln.classList.toggle('hot', inRule(hotRule));
  });
  const target = selRule || hotRule || cur.rule;
  if (target && S.ruleOf[target]) {
    const ln = document.querySelector(`#grammarBody .ln[data-l="${S.ruleOf[target].a}"]`);
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
  drawUnder(); drawOver(); drawChart(); drawSpine(); litRules();
  const state = cur.playing ? 'playing' : (cur.t >= S.doc.length ? 'complete' : 'paused');
  const line = lineOf(Math.min(Math.floor(cur.t), S.doc.length - 1)) + 1;
  $('pos').textContent =
    `char ${Math.floor(Math.min(cur.t, S.doc.length)).toLocaleString()} / ${S.doc.length.toLocaleString()}`
    + ` · line ${line.toLocaleString()} / ${S.lineStarts.length.toLocaleString()} · ${state} · gen ${S.meta.generation}`;
  const focus = cur.sel >= 0 ? cur.sel : cur.hover;
  $('readout').textContent = focus < 0 ? (cur.rule ? `rule ${cur.rule} — its spans outlined violet` : '') : spanWords(focus);
  if (performance.now() - lastPost > 300) {
    lastPost = performance.now();
    fetch('/cursor', { method: 'POST', body: `t ${cur.t.toFixed(1)} sel ${cur.sel}` }).catch(() => {});
  }
}

/* ── pinned windows — pin only for simultaneity ── */

const PIN_CAP = 3;

function addPin(spanIdx) {
  if (spanIdx < 0) return;
  if (pins.length >= PIN_CAP) {
    const banner = $('banner');
    banner.hidden = false;
    banner.className = 'refuse';
    banner.textContent = `pinned ${PIN_CAP} of ${PIN_CAP} — close one first; pin only for simultaneity`;
    return;
  }
  const s = S.spans[spanIdx];
  pins.push({
    id: ++pinSeq, gen: S.meta.generation, s: s.s, e: s.e, d: s.d,
    rule: S.ruleNames[s.r], field: S.fieldNames[s.f] || '',
    snip: S.doc.slice(s.s, Math.min(s.e, s.s + 400)),
    x: 240 + pins.length * 44, y: 110 + pins.length * 44,
  });
  renderPins();
}

function pinSpanIdx(p) {
  if (p.gen !== S.meta.generation) return -1;
  return S.spans.findIndex((s) => s.s === p.s && s.e === p.e && s.d === p.d);
}

function ruleDefText(rule) {
  const def = S.ruleOf[rule];
  if (!def) return '';
  return S.readerLines.slice(def.a, Math.min(def.b + 1, def.a + 3)).join('\n');
}

function renderPins() {
  const layer = $('pinlayer');
  layer.textContent = '';
  for (const p of pins) {
    const stale = p.gen !== S.meta.generation;
    const el = document.createElement('div');
    el.className = 'pin' + (stale ? ' stale' : '');
    el.dataset.id = p.id;
    el.style.left = p.x + 'px';
    el.style.top = p.y + 'px';
    el.style.zIndex = pinZ;
    el.innerHTML =
      `<header><span>${p.rule}</span><span class="addr">${p.s.toLocaleString()}..${p.e.toLocaleString()} · d${p.d}</span>`
      + (stale ? `<span class="stalemark">gen ${p.gen} — stale</span>` : '')
      + `<button class="x" title="close">×</button></header>`
      + `<div class="body"><div class="snip"></div>`
      + `<div class="facts">${p.field ? 'field ' + p.field + ' · ' : ''}pinned against gen ${p.gen}`
      + (stale ? ' · the document has moved on — re-pin or close' : '') + `</div>`
      + `<div class="def"></div></div>`;
    el.querySelector('.snip').textContent = p.snip + (p.e - p.s > 400 ? ' …' : '');
    el.querySelector('.def').textContent = stale ? '' : ruleDefText(p.rule);
    layer.appendChild(el);
  }
  $('pincount').textContent = pins.length ? `pinned ${pins.length} of ${PIN_CAP}` : '';
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
  cur.t = Math.min(cur.t + (S.doc.length / 22) * dt, S.doc.length);
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
  if (!sel.rangeCount || sel.isCollapsed) { cur.docSel = null; return; }
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
  ask();
}

function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) { e.preventDefault(); commitDoc(true); return; }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); commitDoc(false); return; }
  if (e.key === 'Escape') { e.preventDefault(); revertOrClear(); return; }
  if (document.activeElement === $('docText')) return;
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
  pollRoutes();
  const q = new URLSearchParams(location.search);
  if (q.has('t')) { cur.t = Math.min(+q.get('t'), S.doc.length); cur.follow = true; ask(); }
  if (q.has('sel')) { cur.sel = deepestAt(+q.get('sel')); ask(); }
  if (q.has('rule')) { cur.rule = q.get('rule'); ask(); }
  if (q.has('break')) { const off = +q.get('break'); applyEdit(off, off + 1, '\u00a7'); }
  if (q.has('pin')) {
    for (const off of q.get('pin').split(',')) addPin(deepestAt(+off));
  }
  else setTimeout(play, 600);
})();
