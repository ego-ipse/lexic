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
let gView = 'depth3d';
let gTune = { levelstep: 150, ringscale: 1, flatten: 0.78, labelscale: 1 };
const policyTimers = {};

let policySnap = null;
let lastLocalPost = 0;

function postPolicy(key, value) {
  lastLocalPost = performance.now();
  if (policySnap) {
    if (value === '-') delete policySnap[key];
    else policySnap[key] = String(value);
  }
  fetch('/policy', { method: 'POST', body: `${key} ${value}` }).catch(() => {});
}

function postPolicyDebounced(key, value, ms = 350) {
  clearTimeout(policyTimers[key]);
  policyTimers[key] = setTimeout(() => postPolicy(key, value), ms);
}

function setSpeed(x) {
  speed = Math.max(1 / 512, Math.min(16, x));
  postPolicy('speed', speed);
  ask();
}
let pinSeq = 0;
let pinZ = 30;
let view0 = 0;           // chart viewport (leaf-local)
let chartZoom = 1;       // plain scroll on the chart: zoom the lane window
let chartClock = 'model';  // model | pda | earley — which clock the lanes tell
let clockHover = -1;       // hovered document position in a clock view
let clockHoverExt = null;  // the hovered frame / hypothesis extent
let clockData = null;      // { gen, enters, tries, items, entersTop, itemsTop, pdaEnd }
let clockWaiting = false;
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
  scene.policy = {};
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
    } else if (tag === '#POLICY') {
      for (const ln of lines) {
        const sp = ln.indexOf(' ');
        scene.policy[ln.slice(0, sp)] = ln.slice(sp + 1);
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

async function loadClock() {
  if (clockWaiting) return;
  clockWaiting = true;
  try {
    const text = await (await fetch('/clock')).text();
    if (text.startsWith('status pending')) {
      setTimeout(() => { clockWaiting = false; ask(); }, 1500);
      return;
    }
    const data = {
      gen: S.meta.generation, pdaEnd: -1, dropped: 0,
      frames: [], events: [], hyp: [], fnames: [], hnames: [], frameRows: 1, hypRows: 1,
    };
    let section = '';
    for (const ln of text.split('\n')) {
      if (ln.startsWith('generation ')) {
        if (ln.slice(11) !== S.meta.generation) { setTimeout(() => { clockWaiting = false; ask(); }, 1500); return; }
      } else if (ln.startsWith('pda_end ')) data.pdaEnd = +ln.slice(8);
      else if (ln.startsWith('dropped ')) data.dropped = +ln.slice(8);
      else if (ln.startsWith('#PDAFRAMES')) section = 'f';
      else if (ln.startsWith('#PDANAMES')) section = 'fn';
      else if (ln.startsWith('#EVENTS')) section = 't';
      else if (ln.startsWith('#EARLEYNAMES')) section = 'hn';
      else if (ln.startsWith('#EARLEY')) section = 'h';
      else if (section === 'f') {
        const [a, b, c, d, e] = ln.split(' ');
        data.frames.push({ s: +a, e: +b, d: +c, n: +d, cid: +e });
        data.frameRows = Math.max(data.frameRows, +c + 1);
      } else if (section === 'fn') data.fnames.push(ln);
      else if (section === 't') {
        const m = ln.match(/^(\d+) (\S+) (.*)$/);
        if (m) data.events.push({ pos: +m[1], kind: m[2], detail: m[3] });
      } else if (section === 'h') {
        const [a, b, c, d] = ln.split(' ');
        data.hyp.push({ s: +a, e: +b, c: +c, n: +d });
      } else if (section === 'hn') data.hnames.push(ln);
    }
    for (const f of data.frames) f.name = data.fnames[f.n];
    // hypotheses pack into rows greedily — the row count IS the maximum
    // number of simultaneously live hypotheses, itself a measurement
    const rowEnd = [];
    for (const hh of data.hyp) {
      hh.name = data.hnames[hh.n];
      let r = 0;
      while (r < rowEnd.length && rowEnd[r] > hh.s) r++;
      rowEnd[r] = Math.max(hh.e, hh.s + 0.5);
      hh.row = r;
    }
    data.hypRows = Math.max(1, rowEnd.length);
    clockData = data;
    clockWaiting = false;
    ask();
  } catch { clockWaiting = false; }
}

function clockReady() {
  return clockData && clockData.gen === S.meta.generation;
}

let clockHit = null;

function drawClockLanes(cx, w, h, lanesY, pitch, sx) {
  const pda = chartClock === 'pda';
  const list = pda ? clockData.frames : clockData.hyp;
  const rows = pda ? clockData.frameRows : clockData.hypRows;
  const y1 = h - 6;
  const laneH = Math.max(2, Math.min(16, Math.floor((y1 - lanesY - 4) / Math.max(1, rows))));
  const win = S.chartHit.win;
  clockHit = { lanesY: lanesY + 4, laneH, pda };
  const abandoned = 'rgba(224,96,96,0.55)';
  const abandonedFill = 'rgba(224,96,96,0.16)';
  for (const f of list) {
    if (f.e <= view0 || f.s >= view0 + win) continue;
    const row = pda ? f.d : f.row;
    const y = clockHit.lanesY + row * laneH;
    if (y + laneH > y1) continue;
    const x1 = sx(Math.max(f.s, view0));
    const x2 = Math.max(sx(Math.min(f.e, view0 + win)), x1 + 1.5);
    const done = f.e <= cur.t, live = !done && f.s < cur.t;
    if (pda) {
      if (done) { cx.fillStyle = C.closed; cx.fillRect(x1, y, x2 - x1, laneH - 1); cx.strokeStyle = C.cool; }
      else if (live) {
        cx.fillStyle = C.active;
        cx.fillRect(x1, y, sx(Math.min(cur.t, view0 + win)) - x1, laneH - 1);
        cx.strokeStyle = C.warm;
      } else cx.strokeStyle = C.pending;
    } else if (f.c) {
      if (done) { cx.fillStyle = C.closed; cx.fillRect(x1, y, x2 - x1, laneH - 1); }
      cx.strokeStyle = done ? C.cool : C.pending;
    } else {
      if (done) { cx.fillStyle = abandonedFill; cx.fillRect(x1, y, x2 - x1, laneH - 1); }
      cx.strokeStyle = abandoned;
    }
    cx.strokeRect(x1 + 0.5, y + 0.5, Math.max(x2 - x1 - 1, 1.5), laneH - 1);
    if (clockHoverExt === f) {
      cx.strokeStyle = C.ink || '#e8e2d6';
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 2);
    }
    if (markedRule() && f.name === markedRule()) {
      cx.strokeStyle = C.violet;
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 2);
    }
  }
  if (pda) {
    cx.fillStyle = C.warm;
    for (const ev of clockData.events) {
      if (ev.pos < view0 || ev.pos > view0 + win) continue;
      cx.fillRect(sx(ev.pos), lanesY - 2, Math.max(2, pitch / 2), 4);
    }
  }
  if (pda && clockData.pdaEnd >= 0 && clockData.pdaEnd >= view0 && clockData.pdaEnd <= view0 + win) {
    cx.strokeStyle = C.red || '#e06060';
    cx.beginPath(); cx.moveTo(sx(clockData.pdaEnd), lanesY); cx.lineTo(sx(clockData.pdaEnd), y1); cx.stroke();
  }
  cx.fillStyle = C.dim;
  cx.font = '10px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
  const legend = pda
    ? `the PDA's own frames — every push, at its stack depth · gaps: frameless leaf runs · warm ticks: real attempt forks${clockData.pdaEnd >= 0 ? ' · red: where the fast road stops' : ''}`
    : `Earley's hypotheses — every (rule, origin) it considered · red outline: abandoned · ${clockData.hypRows} live at the widest`
      + (clockData.dropped ? ` · ${clockData.dropped.toLocaleString()} short extents not shipped` : '');
  cx.fillText(legend, 12, lanesY - 8);
}

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
  if (chartClock !== 'model') {
    if (!clockReady()) {
      loadClock();
      cx.fillStyle = C.dim;
      cx.fillText(`the ${chartClock} clock is running…`, 12, lanesY + 14);
    } else {
      drawClockLanes(cx, w, h, lanesY, pitch, sx);
    }
    const cxx0 = sx(Math.min(Math.max(cur.t, view0), view0 + win));
    cx.strokeStyle = C.warm;
    cx.beginPath(); cx.moveTo(cxx0, lanesY - 6); cx.lineTo(cxx0, h - 4); cx.stroke();
    return;
  }
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
let colCache = new Map();
let colWaiting = false;

async function fetchColumn(i) {
  if (colCache.has(i) || colWaiting) return;
  colWaiting = true;
  try {
    const text = await (await fetch('/column?i=' + i)).text();
    if (!text.startsWith('#COLUMN')) { colWaiting = false; return; }
    const items = [], expect = [];
    let section = 'c';
    for (const ln of text.split('\n').slice(1)) {
      if (ln.startsWith('#EXPECT')) { section = 'e'; continue; }
      if (section === 'c') {
        const m = ln.match(/^(\d+) (\S+) (.*)$/);
        if (m) items.push({ origin: +m[1], role: m[2], rule: m[3] });
      } else if (ln) expect.push(ln);
    }
    colCache.set(i, { items, expect });
  } catch { /* retry on next cursor move */ }
  colWaiting = false;
  ask();
}

function spineClock(head) {
  $('spineHead').textContent = head;
}

function drawPdaSpine() {
  const body = $('spineBody');
  const closedBody = $('closedBody');
  if (!clockReady()) {
    spineClock('the PDA at t — clock running…');
    body.innerHTML = '<div class="none">the pda clock is still running</div>';
    closedBody.textContent = '';
    return;
  }
  spineClock("the PDA's stack at t");
  const t = cur.t;
  const open = clockData.frames.filter((f) => f.s <= t && t < f.e).sort((a, b) => a.d - b.d);
  body.textContent = '';
  if (!open.length) {
    body.innerHTML = '<div class="none">no frame open — a frameless leaf run carries this stretch</div>';
  }
  open.forEach((f, k) => {
    const row = document.createElement('div');
    row.className = 'row' + (k === open.length - 1 ? ' deep' : '');
    row.innerHTML = `<span class="d">d${f.d}</span>${f.name} <span class="f">${f.s.toLocaleString()}..${f.e.toLocaleString()}</span>`;
    body.appendChild(row);
  });
  closedBody.textContent = '';
  $('closedHead').textContent = 'DECISIONS';
  const evs = clockData.events.filter((e) => e.pos <= t).slice(-7);
  if (!clockData.events.length) {
    closedBody.innerHTML = '<div class="none">none — the whole walk is deterministic descent;'
      + ' the automaton view shows where decisions COULD arise</div>';
  }
  for (const e of evs) {
    const row = document.createElement('div');
    row.className = 'row' + (Math.abs(e.pos - t) < 2 ? ' fresh' : '');
    row.innerHTML = `<span class="d">@${e.pos}</span>${e.kind} <span class="f">${e.detail}</span>`;
    closedBody.appendChild(row);
  }
}

function drawEarleySpine() {
  const i = Math.min(Math.floor(cur.t), S.doc.length);
  const col = colCache.get(i);
  const body = $('spineBody');
  const closedBody = $('closedBody');
  if (!col) {
    fetchColumn(i);
    spineClock(`Earley column ${i} — loading…`);
    return;
  }
  spineClock(`Earley column ${i} — ${col.items.length} items`);
  body.textContent = '';
  if (!col.items.length) {
    body.innerHTML = '<div class="none">empty — inside a lexical run; the kernel scanned past this column</div>';
  }
  for (const it of col.items.slice(0, 40)) {
    const row = document.createElement('div');
    row.className = 'row role-' + it.role;
    row.innerHTML = `<span class="d">@${it.origin}</span><span class="dr">${it.rule}</span>`
      + `<span class="f">${it.role}</span>`;
    body.appendChild(row);
  }
  if (col.items.length > 40) {
    const row = document.createElement('div');
    row.className = 'none';
    row.textContent = `+${col.items.length - 40} more items`;
    body.appendChild(row);
  }
  $('closedHead').textContent = 'CAN COME NEXT';
  closedBody.textContent = '';
  for (const term of col.expect) {
    const chip = document.createElement('span');
    chip.className = 'echip';
    chip.textContent = term;
    closedBody.appendChild(chip);
  }
  if (!col.expect.length) closedBody.innerHTML = '<div class="none">nothing — every item is complete</div>';
}

function drawSpine() {
  if (chartClock === 'pda') { lastSpineKey = ''; drawPdaSpine(); return; }
  if (chartClock === 'earley') { lastSpineKey = ''; drawEarleySpine(); return; }
  spineClock('open at the cursor');
  $('closedHead').textContent = 'JUST CLOSED';
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
  let words = focus < 0 ? (cur.rule ? `rule ${cur.rule} — its spans outlined violet` : '') : spanWords(focus);
  if (chartClock !== 'model' && clockHover >= 0 && clockReady()) {
    const f = clockHoverExt;
    const clk = !f
      ? (chartClock === 'pda' ? 'frameless here — a leaf run carried this stretch' : 'no hypothesis on this row here')
      : chartClock === 'pda'
        ? `frame ${f.name} · ${f.s.toLocaleString()}..${f.e.toLocaleString()} · stack depth ${f.d}`
        : `hypothesis ${f.name} · ${f.s.toLocaleString()}..${f.e.toLocaleString()} · ${f.c ? 'completed' : 'ABANDONED — considered, never finished'}`;
    words = clk + (words ? ` · ${words}` : '');
  }
  $('readout').textContent = words;
  if (performance.now() - lastPost > 300) {
    lastPost = performance.now();
    fetch('/cursor', { method: 'POST', body: `t ${cur.t.toFixed(1)} sel ${cur.sel}` }).catch(() => {});
  }
}

/* ── policy application: the leaf is an interpreter of session state ── */

function applyPolicy() {
  const P = S.policy || {};
  if (P['speed']) speed = parseFloat(P['speed']) || speed;
  if (P['doc.zoom']) { docZoom = parseFloat(P['doc.zoom']) || 1; applyDocZoom(); }
  if (P['chart.zoom']) chartZoom = parseFloat(P['chart.zoom']) || 1;
  if (P['chart.clock']) { chartClock = P['chart.clock']; $('cclock').value = chartClock; }
  if (P['spine.zoom']) { spineZoom = parseFloat(P['spine.zoom']) || 1; applySpineZoom(); }
  if (P['graph.view']) gView = P['graph.view'];
  for (const k of ['levelstep', 'ringscale', 'flatten', 'labelscale']) {
    if (P['graph.' + k]) gTune[k] = parseFloat(P['graph.' + k]);
  }
  document.documentElement.style.setProperty('--glabel', gTune.labelscale);
  for (const which of ['reader', 'right', 'top']) {
    if (P['arrange.' + which]) setShare(which, parseFloat(P['arrange.' + which]), false);
  }
  if (P['graph.camera'] && gViews[0]) {
    const [yw, pt, zm, px, py] = P['graph.camera'].split(' ').map(parseFloat);
    Object.assign(gViews[0], { yaw: yw, pitch: pt, zoom: zm });
    if (!Number.isNaN(px)) gViews[0].pan = { x: px, y: py || 0 };
  }
  if (P['reader.mode'] === 'graph' && !graphOn) setGraph(true, true);
  syncTunePanel();
  rebuildPinsFromPolicy(P);
}

function rebuildPinsFromPolicy(P) {
  const wanted = Object.keys(P).filter((k) => k.startsWith('pin.'));
  if (!wanted.length) return;
  pins = [];
  for (const key of wanted) {
    const id = +key.slice(4);
    pinSeq = Math.max(pinSeq, id);
    pins.push(parsePinValue(id, P[key].split(' ')));
  }
  renderPins();
}

function setShare(which, frac, post = true) {
  const vars = { reader: '--ar', right: '--aright', top: '--atop' };
  const lim = { reader: [0.06, 0.86], right: [0.06, 0.86], top: [0.12, 0.92] };
  const v = Math.max(lim[which][0], Math.min(lim[which][1], frac));
  document.documentElement.style.setProperty(vars[which], (v * 100).toFixed(1) + '%');
  if (post) postPolicyDebounced('arrange.' + which, v.toFixed(3));
  ask();
}

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
  for (const [lvl, list] of levels) {
    list.forEach((n, i) => {
      gFlat.set(n, {
        x: lvl * gTune.levelstep * 1.15,
        y: (i - list.length / 2) * 24 * gTune.ringscale + (lvl % 2) * 9,
      });
    });
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
  if (mode !== 'depth3d') fitk = Math.max(fitk, 0.8);  // flat/arcs stay readable; pan explores
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

/* ── the railroad — one rule's body as track: sequence rides the line,
   choice splits it, repetition loops it. Structure from the wire; geometry here. ── */

const RAIL = { bh: 20, padx: 7, gap: 16, vgap: 9, loop: 13 };
const railCache = new Map();
let railInk = null;

function railColors() {
  if (!railInk) {
    const cs = getComputedStyle(document.documentElement);
    railInk = Object.fromEntries(['cool', 'warm', 'violet', 'dim', 'dimmer', 'ink', 'red', 'field']
      .map((k) => [k, cs.getPropertyValue('--' + k).trim()]));
  }
  return railInk;
}

function railFont() {
  return '11px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
}

async function fetchRail(rule) {
  if (railCache.has(rule)) return railCache.get(rule);
  const text = await fetch('/rail?rule=' + encodeURIComponent(rule)).then((r) => r.text());
  if (text.startsWith('no such rule')) { railCache.set(rule, null); return null; }
  const root = { k: 'seq', payload: '', kids: [] };
  const stack = [root];
  for (const ln of text.split('\n').slice(1)) {
    const m = ln.match(/^(\d+) (\S+)(?: (.*))?$/);
    if (!m) continue;
    const node = { k: m[2], payload: m[3] || '', kids: [] };
    stack[+m[1]].kids.push(node);
    stack[+m[1] + 1] = node;
  }
  const tree = root.kids.length === 1 ? root.kids[0] : root;
  railCache.set(rule, tree);
  return tree;
}

function railMeasure(n, cx) {
  for (const kid of n.kids) railMeasure(kid, cx);
  if (n.k === 'seq') {
    n.cy = Math.max(...n.kids.map((kid) => kid.cy));
    n.w = n.kids.reduce((a, kid) => a + kid.w, 0) + RAIL.gap * (n.kids.length - 1);
    n.h = n.cy + Math.max(...n.kids.map((kid) => kid.h - kid.cy));
  } else if (n.k === 'alt') {
    n.w = Math.max(...n.kids.map((kid) => kid.w)) + 56;
    n.h = n.kids.reduce((a, kid) => a + kid.h, 0) + RAIL.vgap * (n.kids.length - 1);
    n.cy = n.kids[0].cy;
  } else if (n.k === 'many') {
    const [lo, hi] = n.payload.split(' ').map(Number);
    const kid = n.kids[0];
    n.bypass = lo === 0;
    n.loop = hi !== 1;
    n.count = lo > 1 || hi > 1 ? `${lo}..${hi < 0 ? '∞' : hi}` : '';
    n.w = kid.w + 40;
    n.h = kid.h + (n.bypass ? RAIL.loop : 0) + (n.loop ? RAIL.loop : 0) + (n.count ? 10 : 0);
    n.cy = kid.cy + (n.bypass ? RAIL.loop : 0);
  } else if (n.k === 'not' || n.k === 'alpha') {
    const kid = n.kids[0];
    n.tag = n.k === 'not' ? '¬ none of' : '⟨' + n.payload + '⟩';
    n.w = Math.max(kid.w + 12, cx.measureText(n.tag).width + 12);
    n.h = kid.h + 20;
    n.cy = kid.cy + 16;
  } else {
    let label = n.k === 'nil' ? 'ε' : n.k === 'class' ? '[' + n.payload + ']' : n.payload || 'ε';
    if (label.length > 30) label = label.slice(0, 29) + '…';
    n.label = label;
    n.w = Math.max(26, Math.ceil(cx.measureText(label).width) + RAIL.padx * 2);
    n.h = RAIL.bh;
    n.cy = RAIL.bh / 2;
  }
}

function railLine(cx, x0, y0, x1, y1) {
  cx.strokeStyle = railColors().dim;
  cx.lineWidth = 1.2;
  cx.beginPath();
  cx.moveTo(x0, y0);
  cx.lineTo(x1, y1);
  cx.stroke();
}

function railBranch(cx, x0, y0, x1, y1) {
  cx.strokeStyle = railColors().dim;
  cx.lineWidth = 1.2;
  cx.beginPath();
  cx.moveTo(x0, y0);
  cx.bezierCurveTo((x0 + x1) / 2, y0, (x0 + x1) / 2, y1, x1, y1);
  cx.stroke();
}

function railArch(cx, x0, x1, y, dy) {
  cx.strokeStyle = railColors().dim;
  cx.lineWidth = 1.2;
  cx.beginPath();
  cx.moveTo(x0, y);
  cx.bezierCurveTo(x0 + 2, y + dy, x1 - 2, y + dy, x1, y);
  cx.stroke();
}

function railDraw(n, cx, x, y, hits) {
  const yE = y + n.cy;
  if (n.k === 'seq') {
    let ax = x;
    n.kids.forEach((kid, i) => {
      if (i) { railLine(cx, ax, yE, ax + RAIL.gap, yE); ax += RAIL.gap; }
      railDraw(kid, cx, ax, yE - kid.cy, hits);
      ax += kid.w;
    });
  } else if (n.k === 'alt') {
    const inx = x + 28, outx = x + n.w - 28;
    let ay = y;
    for (const kid of n.kids) {
      const ky = ay + kid.cy;
      railBranch(cx, x, yE, inx, ky);
      railDraw(kid, cx, inx, ay, hits);
      railLine(cx, inx + kid.w, ky, outx, ky);
      railBranch(cx, x + n.w, yE, outx, ky);
      ay += kid.h + RAIL.vgap;
    }
  } else if (n.k === 'many') {
    const kid = n.kids[0];
    const kx = x + 20;
    railLine(cx, x, yE, kx, yE);
    railDraw(kid, cx, kx, yE - kid.cy, hits);
    railLine(cx, kx + kid.w, yE, x + n.w, yE);
    if (n.bypass) railArch(cx, x + 5, x + n.w - 5, yE, -(kid.cy + 10));
    if (n.loop) railArch(cx, kx - 6, kx + kid.w + 6, yE, kid.h - kid.cy + 10);
    if (n.count) {
      cx.fillStyle = railColors().dim;
      cx.fillText(n.count, x + (n.w - cx.measureText(n.count).width) / 2, yE + kid.h - kid.cy + RAIL.loop + 8);
    }
  } else if (n.k === 'not' || n.k === 'alpha') {
    const kid = n.kids[0];
    const kx = x + 6;
    railLine(cx, x, yE, kx, yE);
    railDraw(kid, cx, kx, y + 16, hits);
    railLine(cx, kx + kid.w, yE, x + n.w, yE);
    cx.setLineDash([3, 3]);
    cx.strokeStyle = railColors().dim;
    cx.strokeRect(x + 1, y + 1, n.w - 2, n.h - 2);
    cx.setLineDash([]);
    cx.fillStyle = n.k === 'not' ? railColors().red : railColors().dim;
    cx.fillText(n.tag, x + 5, y + 11);
  } else {
    const C = railColors();
    let color = { ref: C.cool, lit: C.warm, class: C.violet }[n.k] || C.dim;
    let textColor = color;
    if (n.k === 'ref' && n.label === hotRule()) {
      // the same light the rule's chip carries when hovered
      cx.fillStyle = C.warm;
      cx.fillRect(x, y, n.w, n.h);
      color = C.warm;
      textColor = C.field;
    } else if (n.k === 'ref' && n.label === cur.rule) {
      color = C.violet;
      textColor = C.violet;
    }
    cx.strokeStyle = color;
    cx.lineWidth = 1;
    cx.beginPath();
    if (n.k === 'lit') cx.roundRect(x, y, n.w, n.h, 9);
    else cx.rect(x, y, n.w, n.h);
    cx.stroke();
    cx.fillStyle = textColor;
    cx.fillText(n.label, x + (n.w - cx.measureText(n.label).width) / 2, yE + 3.5);
    if (n.k === 'ref') hits.push({ x, y, w: n.w, h: n.h, rule: n.label });
  }
}

let railsAll = null;
let railsLoading = false;
let railsLayout = null;

function parseRailTree(lines) {
  const root = { k: 'seq', payload: '', kids: [] };
  const stack = [root];
  for (const ln of lines) {
    const m = ln.match(/^(\d+) (\S+)(?: (.*))?$/);
    if (!m) continue;
    const node = { k: m[2], payload: m[3] || '', kids: [] };
    stack[+m[1]].kids.push(node);
    stack[+m[1] + 1] = node;
  }
  return root.kids.length === 1 ? root.kids[0] : root;
}

async function fetchRails() {
  if (railsAll || railsLoading) return;
  railsLoading = true;
  const text = await fetch('/rails').then((r) => r.text());
  railsAll = new Map();
  let name = null, lines = [];
  for (const ln of text.split('\n')) {
    if (ln.startsWith('#RAIL ')) {
      if (name !== null) railsAll.set(name, parseRailTree(lines));
      name = ln.split(' ')[1];
      lines = [];
    } else {
      lines.push(ln);
    }
  }
  if (name !== null) railsAll.set(name, parseRailTree(lines));
  railsLayout = null;
  drawGraph();  // one redraw, when the rails arrive
}

function railsOrder() {
  const names = Object.keys(S.depths).length ? Object.keys(S.depths) : S.ruledefs.map((r) => r.name);
  const order = S.ruledefs.map((r) => r.name).filter((n) => names.includes(n));
  for (const n of names) if (!order.includes(n)) order.push(n);
  return order;
}

function buildRailsLayout(cx) {
  cx.font = railFont();
  const gap = 10 + gTune.levelstep / 8;
  const entries = [];
  let y = 0, maxw = 0;
  for (const name of railsOrder()) {
    const tree = railsAll.get(name);
    if (!tree) continue;
    railMeasure(tree, cx);
    entries.push({ rule: name, tree, x: 26, y: y + 14 });
    maxw = Math.max(maxw, tree.w + 66);
    y += 14 + tree.h + gap;
  }
  railsLayout = { entries, byName: new Map(entries.map((e) => [e.rule, e])), w: maxw, h: y };
}

function drawRailsView(v) {
  const wrap = v.wrap, cv = v.cv;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w || !h) return;
  if (!railsAll) { fetchRails(); return; }  // a guarded call schedules nothing
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const cx = cv.getContext('2d');
  if (!railsLayout) buildRailsLayout(cx);
  const L = railsLayout;
  const k = Math.max(Math.min((w - 24) / Math.max(60, L.w), 1.35), 0.8) * v.zoom;
  const mx = L.w / 2, my = L.h / 2;
  if (!v.touched) {
    v.pan.x = 16 - w / 2 + mx * k;  // untouched camera frames the top-left —
    v.pan.y = 12 - h / 2 + my * k;  // the start rule; pan explores downward
  }
  const tx = w / 2 - mx * k + v.pan.x, ty = h / 2 - my * k + v.pan.y;
  v.rk = k; v.rtx = tx; v.rty = ty;
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  cx.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);
  cx.font = railFont();
  const hits = [];
  const uy0 = -ty / k - 40, uy1 = (h - ty) / k + 40;
  for (const e of L.entries) {
    if (e.y + e.tree.h < uy0 || e.y > uy1) continue;
    const yE = e.y + e.tree.cy;
    railLine(cx, e.x - 14, yE, e.x, yE);
    railLine(cx, e.x + e.tree.w, yE, e.x + e.tree.w + 14, yE);
    cx.fillStyle = railColors().dim;
    for (const ex of [e.x - 14, e.x + e.tree.w + 14]) {
      cx.beginPath();
      cx.arc(ex, yE, 2.5, 0, Math.PI * 2);
      cx.fill();
    }
    railDraw(e.tree, cx, e.x, e.y, hits);
  }
  v.railHits = hits;
  const start = Object.keys(S.depths).find((n) => S.depths[n] === 0) || '';
  const hot = hotRule();
  for (const el of v.chips.children) {
    const e = L.byName.get(el.dataset.name);
    if (!e) { el.style.display = 'none'; continue; }
    el.style.display = '';
    el.style.left = (e.x - 12) * k + tx + 'px';
    el.style.top = (e.y - 6) * k + ty + 'px';
    el.style.transform = 'translate(0, -100%)';
    el.style.zIndex = 5;
    el.classList.add('near');
    el.classList.remove('dot');
    el.classList.toggle('start', el.dataset.name === start);
    el.classList.toggle('marked', el.dataset.name === cur.rule);
    el.classList.toggle('hot', el.dataset.name === hot);
    el.classList.remove('faded');
  }
}

let railChipRule = '';

function railChipShow(rule, x, y) {
  railChipRule = rule;
  const chip = $('railchip');
  chip.style.left = Math.max(8, Math.min(x + 6, window.innerWidth - 86)) + 'px';
  chip.style.top = Math.max(8, Math.min(y - 34, window.innerHeight - 42)) + 'px';
  chip.hidden = false;
}

function wireRailChip() {
  const chip = $('railchip');
  chip.addEventListener('pointerdown', (e) => e.preventDefault());
  chip.addEventListener('click', () => {
    if (railChipRule) railPin(railChipRule);
    chip.hidden = true;
  });
  window.addEventListener('pointerdown', (e) => {
    if (!e.target.closest('#railchip')) chip.hidden = true;
  }, true);
  $('grammarScroll').addEventListener('scroll', () => { chip.hidden = true; });
}

function railsGoto(v, rule) {
  const e = railsLayout && railsLayout.byName.get(rule);
  if (!e || v.rk === undefined) return;
  v.touched = true;
  v.pan.y += 34 - (e.y * v.rk + v.rty);
  persistView(v);
  drawGraphView(v);
}

/* ── the automaton view — the compiled machine itself, walk-lit at t ── */

let autoData = null;
let autoLoading = false;

async function fetchAutomaton() {
  if (autoData || autoLoading) return;
  autoLoading = true;
  const text = await (await fetch('/automaton')).text();
  const clones = [], names = [], edges = [];
  let section = '';
  for (const ln of text.split('\n')) {
    if (ln.startsWith('#ACLONES')) section = 'c';
    else if (ln.startsWith('#ANAMES')) section = 'n';
    else if (ln.startsWith('#AEDGES')) section = 'e';
    else if (section === 'c') {
      const [ni, mode, flags, depth] = ln.split(' ');
      clones.push({ n: +ni, mode, flags, depth: +depth });
    } else if (section === 'n') names.push(ln);
    else if (section === 'e') {
      const [a, b] = ln.split(' ');
      edges.push([+a, +b]);
    }
  }
  const levels = new Map();
  for (const c of clones) {
    c.name = names[c.n];
    const d = c.depth < 0 ? 0 : c.depth;
    if (!levels.has(d)) levels.set(d, []);
    c.li = levels.get(d).length;
    levels.get(d).push(c);
  }
  for (const c of clones) c.ln = levels.get(c.depth < 0 ? 0 : c.depth).length;
  autoData = { clones, edges, maxDepth: Math.max(...levels.keys()) };
  drawGraph();
}

const AUTO_INK = { dispatch: '#6fc3c9', alt: '#e2a65c', seq: '#8fa3b8', value_str: '#d98cf5', group: '#66707f' };

function autoPos(c) {
  const step = gTune.levelstep * 1.15;
  const spread = 15 * gTune.ringscale;
  return { x: (c.depth < 0 ? 0 : c.depth) * step, y: (c.li - c.ln / 2) * spread };
}

function drawAutoView(v) {
  const wrap = v.wrap, cv = v.cv;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w || !h) return;
  if (!autoData) { fetchAutomaton(); return; }
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const cx = cv.getContext('2d');
  const step = gTune.levelstep * 1.15;
  const cw = (autoData.maxDepth + 1) * step;
  const k = Math.max(Math.min((w - 40) / Math.max(120, cw), 1.4), 0.55) * v.zoom;
  const mx = cw / 2, my = 0;
  if (!v.touched) {
    v.pan.x = 24 - w / 2 + mx * k;
    v.pan.y = 0;
  }
  const tx = w / 2 - mx * k + v.pan.x, ty = h / 2 + v.pan.y;
  v.rk = k; v.rtx = tx; v.rty = ty;
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  cx.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);
  // the walk at t: which clones the kernel is IN, has VISITED
  const inNow = new Set(), visited = new Set();
  const lit = chartClock === 'pda' && clockReady();
  if (lit) {
    for (const f of clockData.frames) {
      if (f.cid < 0) continue;
      if (f.s <= cur.t && cur.t < f.e) inNow.add(f.cid);
      else if (f.e <= cur.t) visited.add(f.cid);
    }
  }
  cx.lineWidth = 1 / k;
  for (const [a, b] of autoData.edges) {
    const A = autoPos(autoData.clones[a]), B = autoPos(autoData.clones[b]);
    const hotEdge = inNow.has(a) && inNow.has(b);
    cx.strokeStyle = hotEdge ? 'rgba(226,166,92,0.8)' : 'rgba(111,195,201,0.10)';
    cx.beginPath();
    cx.moveTo(A.x + 4, A.y);
    cx.bezierCurveTo(A.x + step * 0.4, A.y, B.x - step * 0.4, B.y, B.x - 4, B.y);
    cx.stroke();
  }
  cx.font = `${Math.max(8, 10 / Math.sqrt(k))}px ${getComputedStyle(document.documentElement).getPropertyValue('--mono')}`;
  const mark = markedRule();
  v.autoHits = [];
  for (let ci = 0; ci < autoData.clones.length; ci++) {
    const c = autoData.clones[ci];
    const P = autoPos(c);
    const base = AUTO_INK[c.mode] || '#66707f';
    const isIn = inNow.has(ci);
    v.autoHits.push({ x: P.x - 4, y: P.y - 4, w: 8, h: 8, c });
    cx.fillStyle = isIn ? '#e2a65c'
      : visited.has(ci) ? base
      : 'rgba(102,112,127,0.45)';
    if (c.mode === 'dispatch') {
      cx.beginPath(); cx.arc(P.x, P.y, 3.4, 0, Math.PI * 2); cx.fill();
    } else {
      cx.fillRect(P.x - 3, P.y - 3, 6, 6);
    }
    if (c.flags.includes('a')) {
      cx.strokeStyle = '#e2a65c';
      cx.beginPath(); cx.arc(P.x, P.y, 5.5, 0, Math.PI * 2); cx.stroke();
    }
    if (c.flags.includes('k') || c.flags.includes('p') || c.flags.includes('s')) {
      cx.strokeStyle = 'rgba(217,140,245,0.7)';
      cx.strokeRect(P.x - 5, P.y - 5, 10, 10);
    }
    const showLabel = isIn || c.name === mark || c.name === hotRule() || k > 1.15 || c.depth <= 1;
    if (showLabel) {
      cx.fillStyle = isIn ? '#e2a65c' : c.name === mark ? '#d98cf5' : '#66707f';
      cx.fillText(c.name, P.x + 7, P.y + 3);
    }
  }
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.fillStyle = '#66707f';
  cx.font = '10px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
  const litWord = lit ? ` · warm = the stack at t (${inNow.size} in)` : '';
  cx.fillText(
    `the compiled machine — ${autoData.clones.length} clones, ${autoData.edges.length} calls · `
    + `■ seq · ● dispatch · violet value_str · warm ring = attempt clone · violet box = gated${litWord}`,
    12, 14);
}

function railPin(rule) {
  const k = pins.length;
  const p = { id: ++pinSeq, kind: 'rail', rule, x: 320 + (k % 8) * 40, y: 120 + (k % 8) * 40, w: 0, h: 0 };
  pins.push(p);
  renderPins();
}

function railHitAt(p, cv, e) {
  if (!p.hits) return null;
  const r = cv.getBoundingClientRect();
  const ux = (e.clientX - r.left - p.ox) / p.scale;
  const uy = (e.clientY - r.top - p.oy) / p.scale;
  const hit = p.hits.find((b) => ux >= b.x && ux <= b.x + b.w && uy >= b.y && uy <= b.y + b.h);
  return hit ? hit.rule : null;
}

function drawRailPin(p, el) {
  const body = el.querySelector('.railbody');
  const cv = el.querySelector('canvas');
  const w = body.clientWidth, h = body.clientHeight;
  if (!w || !h || !p.tree) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  cv.width = w * dpr;
  cv.height = h * dpr;
  const cx = cv.getContext('2d');
  const full = p.tree.w + 28;
  const s = Math.min(1.5, (w - 20) / full, (h - 16) / p.tree.h);
  p.scale = s;
  p.ox = (w - full * s) / 2 + 14 * s;
  p.oy = (h - p.tree.h * s) / 2;
  cx.setTransform(dpr * s, 0, 0, dpr * s, dpr * p.ox, dpr * p.oy);
  cx.font = railFont();
  p.hits = [];
  const yE = p.tree.cy;
  railLine(cx, -14, yE, 0, yE);
  railLine(cx, p.tree.w, yE, p.tree.w + 14, yE);
  cx.fillStyle = railColors().dim;
  for (const ex of [-14, p.tree.w + 14]) {
    cx.beginPath();
    cx.arc(ex, yE, 2.5, 0, Math.PI * 2);
    cx.fill();
  }
  railDraw(p.tree, cx, 0, 0, p.hits);
}

async function railPinLoad(p, el) {
  const body = el.querySelector('.railbody');
  const cv = el.querySelector('canvas');
  const tree = await fetchRail(p.rule);
  if (!tree) { body.textContent = 'no such rule ' + p.rule; return; }
  p.tree = tree;
  const cx = cv.getContext('2d');
  cx.font = railFont();
  railMeasure(tree, cx);
  if (!p.w) {
    p.w = Math.min(tree.w + 52, Math.floor(window.innerWidth * 0.72));
    p.h = Math.min(tree.h + 58, Math.floor(window.innerHeight * 0.72));
    el.style.width = p.w + 'px';
    el.style.height = p.h + 'px';
  }
  el.querySelector('.addr').textContent = p.rule;
  el.querySelector('.rback').hidden = !(p.hist && p.hist.length);
  const up = el.querySelector('.rup');
  const parents = [...new Set(S.edges.filter((ed) => ed[1] === p.rule && ed[0] !== p.rule).map((ed) => ed[0]))];
  up.hidden = !parents.length;
  up.innerHTML = `<option value="">▲ ${parents.length}</option>`
    + parents.map((n) => `<option>${n}</option>`).join('');
  postPolicyDebounced(`pin.${p.id}`, pinPolicyValue(p));
  drawRailPin(p, el);
}

function railGoto(p, el, rule, push) {
  if (rule === p.rule) return;
  if (push) (p.hist = p.hist || []).push(p.rule);
  p.rule = rule;
  p.tree = null;
  railPinLoad(p, el);
}

async function wireRailPin(p, el) {
  const cv = el.querySelector('canvas');
  new ResizeObserver(() => drawRailPin(p, el)).observe(el.querySelector('.railbody'));
  cv.addEventListener('click', (e) => {
    // navigate in place — a NEW window is the chip gesture's job, not a click's
    const rule = railHitAt(p, cv, e);
    if (rule) railGoto(p, el, rule, true);
  });
  cv.addEventListener('mousemove', (e) => {
    const rule = railHitAt(p, cv, e) || '';
    cv.style.cursor = rule ? 'pointer' : '';
    if (rule !== graphHover) { graphHover = rule; ask(); }
  });
  cv.addEventListener('mouseout', () => {
    if (graphHover) { graphHover = ''; ask(); }
  });
  el.querySelector('.rback').addEventListener('click', () => {
    if (p.hist && p.hist.length) railGoto(p, el, p.hist.pop(), false);
  });
  el.querySelector('.rup').addEventListener('change', (e) => {
    if (e.target.value) railGoto(p, el, e.target.value, true);
    e.target.selectedIndex = 0;
  });
  await railPinLoad(p, el);
}

let spineZoom = 1;

function wireSpineZoom() {
  // text fields zoom with Ctrl+scroll, like an editor
  $('spine').addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    spineZoom = Math.max(0.6, Math.min(2.4, spineZoom * Math.pow(1.0016, -e.deltaY)));
    applySpineZoom();
    postPolicyDebounced('spine.zoom', spineZoom.toFixed(2));
  }, { passive: false });
}

function applySpineZoom() {
  for (const id of ['spineBody', 'closedBody']) {
    $(id).style.fontSize = (11.5 * spineZoom).toFixed(1) + 'px';
  }
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
      postPolicyDebounced('doc.zoom', docZoom.toFixed(2));
      ask();
    }, { passive: false });
  }
}

function wireClockSelect() {
  $('cclock').addEventListener('change', () => {
    chartClock = $('cclock').value;
    postPolicy('chart.clock', chartClock);
    ask();
  });
}

function wireChartZoom() {
  $('chartCv').addEventListener('wheel', (e) => {
    e.preventDefault();
    chartZoom = Math.max(0.25, Math.min(8, chartZoom * Math.pow(1.0016, -e.deltaY)));
    postPolicyDebounced('chart.zoom', chartZoom.toFixed(2));
    ask();
  }, { passive: false });
}

const TUNE_PANEL = {
  depth3d: { levelstep: 'depth', ringscale: 'ring', flatten: 'flat', labelscale: 'label' },
  flat: { levelstep: 'cols', ringscale: 'rows', labelscale: 'label' },
  arcs: { levelstep: 'pitch', ringscale: 'lift', labelscale: 'label' },
  rails: { levelstep: 'gap', labelscale: 'label' },
  automaton: { levelstep: 'depth', ringscale: 'spread', labelscale: 'label' },
};

function syncTunePanel() {
  if (!$('gt-levelstep')) return;
  const panel = TUNE_PANEL[gView] || TUNE_PANEL.depth3d;
  for (const k of ['levelstep', 'ringscale', 'flatten', 'labelscale']) {
    const row = $('gt-' + k).parentElement;
    row.style.display = (k in panel) ? '' : 'none';  // CSS display:grid beats the hidden attribute
    if (k in panel) row.firstChild.textContent = panel[k];
    $('gt-' + k).value = gTune[k];
  }
  $('gview').value = gView;
}

function wireTune() {
  $('gview').addEventListener('change', () => {
    const from = gView;
    gView = $('gview').value;
    if (gViews[0]) {
      switchViewMode(gViews[0], from, gView);
      persistView(gViews[0]);
    }
    postPolicy('graph.view', gView);
    syncTunePanel();
    drawGraph();
  });
  for (const k of ['levelstep', 'ringscale', 'flatten', 'labelscale']) {
    $('gt-' + k).addEventListener('input', (e) => {
      gTune[k] = parseFloat(e.target.value);
      if (k === 'labelscale') {
        document.documentElement.style.setProperty('--glabel', gTune.labelscale);
      } else if (gNodes) {
        buildGraph();
      }
      postPolicyDebounced('graph.' + k, gTune[k]);
      drawGraph();
    });
  }
}

function wireSeams() {
  let seam = null;
  window.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.pin') || e.target.closest('#pinchip')) return;
    const g = $('grid').getBoundingClientRect();
    const rd = $('document').getBoundingClientRect();
    const rc = $('chart').getBoundingClientRect();
    const rs = $('spine').getBoundingClientRect();
    if (Math.abs(e.clientX - rd.left) <= 10 && e.clientY > g.top) seam = 'reader';
    else if (Math.abs(e.clientX - rc.left) <= 10 && e.clientY > g.top) seam = 'right';
    else if (e.clientX >= rc.left && Math.abs(e.clientY - rs.top) <= 8) seam = 'top';
    if (seam) {
      e.preventDefault();
      document.body.style.cursor = seam === 'top' ? 'row-resize' : 'col-resize';
    }
  }, true);
  window.addEventListener('pointermove', (e) => {
    if (!seam) {
      if (e.buttons) return;
      const g = $('grid').getBoundingClientRect();
      if (e.clientY <= g.top) { document.body.style.cursor = ''; return; }
      const rd = $('document').getBoundingClientRect();
      const rc = $('chart').getBoundingClientRect();
      const rs = $('spine').getBoundingClientRect();
      const near =
        (Math.abs(e.clientX - rd.left) <= 10 || Math.abs(e.clientX - rc.left) <= 10) ? 'col-resize'
        : (e.clientX >= rc.left && Math.abs(e.clientY - rs.top) <= 8) ? 'row-resize' : '';
      document.body.style.cursor = near;
      return;
    }
    const g = $('grid').getBoundingClientRect();
    if (seam === 'reader') setShare('reader', (e.clientX - g.left) / g.width);
    else if (seam === 'right') setShare('right', (g.right - e.clientX) / g.width);
    else setShare('top', (e.clientY - g.top) / g.height);
  });
  window.addEventListener('pointerup', () => {
    if (seam) {
      seam = null;
      document.body.style.cursor = '';
    }
  });
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
  const p = {
    id: ++pinSeq, gen: S.meta.generation, s: s.s, e: s.e, d: s.d,
    rule: S.ruleNames[s.r], field: S.fieldNames[s.f] || '',
    snip: S.doc.slice(s.s, Math.min(s.e, s.s + 400)),
    x: 240 + (k % 8) * 44 + Math.floor(k / 8) * 12,
    y: 110 + (k % 8) * 44,
    w: 0,
  };
  pins.push(p);
  renderPins();
  postPolicy(`pin.${p.id}`, pinPolicyValue(p));
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
  if (p.kind === 'rail') {
    if (p.w) el.style.width = p.w + 'px';
    if (p.h) el.style.height = p.h + 'px';
    el.classList.add('rail');
    el.innerHTML =
      `<header><span>RAILROAD</span><span class="addr">${p.rule}</span>`
      + `<button class="rback" title="back" hidden>↩</button><select class="rup" hidden></select>`
      + `<span class="stalemark"></span><button class="x" title="close">×</button></header>`
      + `<div class="body railbody"><canvas></canvas></div>`;
    layer.appendChild(el);
    p.el = el;
    wireRailPin(p, el);
    return el;
  }
  if (p.kind === 'graph') {
    el.style.width = p.w + 'px';
    el.style.height = '440px';
    el.innerHTML =
      `<header><span>RULE GRAPH</span><select class="pview"><option value="depth3d">depth 3d</option>`
      + `<option value="flat">flat</option><option value="arcs">arcs</option><option value="rails">rails</option>`
      + `<option value="automaton">automaton</option><option value="text">text</option></select>`
      + `<span class="stalemark"></span><button class="x" title="close">×</button></header>`
      + `<div class="body gbody"><div class="gwrap"><canvas></canvas><div class="gchips"></div></div>`
      + `<div class="gtext"></div></div>`;
    layer.appendChild(el);
    const wrap = el.querySelector('.gwrap');
    const v = makeGraphView(wrap, el.querySelector('canvas'), el.querySelector('.gchips'));
    v.pin = p;
    p.view = v;
    v.yaw = p.vyaw ?? 0.9;
    if (p.vpitch !== undefined) v.pitch = p.vpitch;
    if (p.vzoom !== undefined) v.zoom = p.vzoom;
    if (p.vpanx) v.pan.x = p.vpanx;
    if (p.vpany) v.pan.y = p.vpany;
    gViews.push(v);
    if (gNodes) buildChipsInto(v.chips);
    wireGraphView(v);
    new ResizeObserver(() => drawGraphView(v)).observe(wrap);
    const sel = el.querySelector('.pview');
    sel.value = p.mode || 'depth3d';
    sel.addEventListener('change', () => {
      const from = p.mode || 'depth3d';
      p.mode = sel.value;
      switchViewMode(v, from, p.mode);
      applyPinMode(p, el);
      postPolicyDebounced(`pin.${p.id}`, pinPolicyValue(p));
    });
    applyPinMode(p, el);
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
  if (p.h) el.style.height = p.h + 'px';
  new ResizeObserver(() => {
    if (el.offsetWidth && (Math.abs(el.offsetWidth - p.w) > 2 || Math.abs(el.offsetHeight - (p.h || el.offsetHeight)) > 2)) {
      p.w = el.offsetWidth;
      p.h = el.offsetHeight;
      postPolicyDebounced(`pin.${p.id}`, pinPolicyValue(p));
    }
  }).observe(el);
  return el;
}

function applyPinMode(p, el) {
  const m = p.mode || 'depth3d';
  el.querySelector('.gwrap').style.display = m === 'text' ? 'none' : '';
  const tx = el.querySelector('.gtext');
  tx.style.display = m === 'text' ? 'block' : 'none';  // CSS default is none
  if (m === 'text' && !tx.textContent) tx.textContent = S.reader;
  if (m !== 'text' && p.view) drawGraphView(p.view);
}

function renderPins() {
  // reconcile, never rebuild: a hand-resized window keeps its size and scroll
  const layer = $('pinlayer');
  const seen = new Set();
  for (const p of pins) {
    seen.add(String(p.id));
    let el = layer.querySelector(`.pin[data-id="${p.id}"]`);
    if (!el) el = buildPin(p, layer);
    if (p.kind) continue;
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
    if (e.target.closest('.pview') || e.target.closest('.rback') || e.target.closest('.rup')) return;
    if (e.target.closest('.x')) {
      pins = pins.filter((p) => p.id !== +el.dataset.id);
      renderPins();
      postPolicy(`pin.${el.dataset.id}`, '-');
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
  window.addEventListener('pointerup', () => {
    if (drag) postPolicyDebounced(`pin.${drag.p.id}`, pinPolicyValue(drag.p));
    drag = null;
  });
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
  $('tb-slow').addEventListener('click', () => setSpeed(speed / 2));
  $('tb-fast').addEventListener('click', () => setSpeed(speed * 2));
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
    if (cur.rule) railChipShow(cur.rule, e.clientX, e.clientY);
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
    let clkh = -1;
    if (y >= lanesY) {
      const off = view0 + (e.clientX - r.left - pad) / pitch;
      if (chartClock === 'model') {
        const d = Math.floor((y - lanesY) / laneH);
        S.spans.forEach((s, i) => { if (s.d === d && s.s <= off && off < s.e) hover = i; });
      } else if (off >= 0 && off <= S.doc.length && clockHit && clockReady()) {
        // a clock lane holds extents: find the one under the hand
        clkh = Math.round(off);
        const row = Math.floor((y - clockHit.lanesY) / clockHit.laneH);
        const list = clockHit.pda ? clockData.frames : clockData.hyp;
        clockHoverExt = list.find((f) => (clockHit.pda ? f.d : f.row) === row && f.s <= off && off < Math.max(f.e, f.s + 1)) || null;
        hover = deepestAt(Math.min(clkh, S.doc.length - 1));
      }
    }
    const hoverName = clockHoverExt ? clockHoverExt.name : '';
    if (hover !== cur.hover || clkh !== clockHover || hoverName !== graphHover) {
      cur.hover = hover;
      clockHover = clkh;
      if (chartClock !== 'model') graphHover = hoverName;
      ask();
    }
  });
  chart.addEventListener('mouseleave', () => {
    if (cur.hover !== -1 || clockHover !== -1 || clockHoverExt) {
      cur.hover = -1; clockHover = -1; clockHoverExt = null;
      if (chartClock !== 'model' && graphHover) graphHover = '';
      ask();
    }
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
  if (e.key === '[') { setSpeed(speed / 2); return; }
  if (e.key === ']') { setSpeed(speed * 2); return; }
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
  applyPolicy();
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

function applyPolicyKey(k, v) {
  if (k === 'speed') speed = parseFloat(v) || 1;
  else if (k === 'doc.zoom') { docZoom = parseFloat(v) || 1; applyDocZoom(); }
  else if (k === 'chart.zoom') chartZoom = parseFloat(v) || 1;
  else if (k === 'chart.clock') { chartClock = v || 'model'; $('cclock').value = chartClock; }
  else if (k === 'spine.zoom') { spineZoom = parseFloat(v) || 1; applySpineZoom(); }
  else if (k === 'reader.mode') setGraph(v === 'graph', true);
  else if (k === 'graph.view') {
    const from = gView;
    gView = v || 'depth3d';
    if (gViews[0]) switchViewMode(gViews[0], from, gView);
    syncTunePanel();
  } else if (k === 'graph.camera' && gViews[0] && v) {
    const [yw, pt, zm, px, py] = v.split(' ').map(parseFloat);
    Object.assign(gViews[0], { yaw: yw, pitch: pt, zoom: zm });
    if (!Number.isNaN(px)) gViews[0].pan = { x: px, y: py || 0 };
    gViews[0].touched = true;
  } else if (k.startsWith('graph.')) {
    const tune = k.slice(6);
    if (tune in gTune && v) {
      gTune[tune] = parseFloat(v);
      if (tune === 'labelscale') document.documentElement.style.setProperty('--glabel', gTune.labelscale);
      else if (gNodes) buildGraph();
      syncTunePanel();
    }
  } else if (k.startsWith('arrange.')) {
    if (v) setShare(k.slice(8), parseFloat(v), false);
  }
}

function parsePinValue(id, t) {
  if (t[0] === 'graph') {
    return {
      id, kind: 'graph', rule: 'RULE GRAPH',
      x: +t[1], y: +t[2], w: +t[3], h: +t[4],
      vyaw: parseFloat(t[5]), vpitch: parseFloat(t[6]), vzoom: parseFloat(t[7]),
      vpanx: parseFloat(t[8]) || 0, vpany: parseFloat(t[9]) || 0,
      mode: t[10] || 'depth3d',
    };
  }
  if (t[0] === 'rail') {
    return { id, kind: 'rail', rule: t[1], x: +t[2], y: +t[3], w: +t[4], h: +t[5] };
  }
  const [se, ee, de] = [+t[1], +t[2], +t[3]];
  return {
    id, gen: t[9] ?? S.meta.generation, s: se, e: ee, d: de, rule: t[4],
    field: '', snip: S.doc.slice(se, Math.min(ee, se + 400)),
    x: +t[5], y: +t[6], w: +t[7], h: +t[8] || 0,
  };
}

function syncPinsFromPolicy(P) {
  const wanted = new Map();
  for (const k of Object.keys(P)) if (k.startsWith('pin.')) wanted.set(+k.slice(4), P[k].split(' '));
  pins = pins.filter((p) => wanted.has(p.id));
  for (const [id, t] of wanted) {
    let p = pins.find((q) => q.id === id);
    if (!p) {
      pinSeq = Math.max(pinSeq, id);
      pins.push(parsePinValue(id, t));
      continue;
    }
    // update in place — el/view/tree/history survive a remote nudge
    const pel = $('pinlayer').querySelector(`.pin[data-id="${p.id}"]`);
    if (t[0] === 'graph') {
      Object.assign(p, { x: +t[1], y: +t[2], w: +t[3], h: +t[4] });
      if (p.view && t.length > 9) {
        Object.assign(p.view, { yaw: parseFloat(t[5]), pitch: parseFloat(t[6]), zoom: parseFloat(t[7]) });
        p.view.pan = { x: parseFloat(t[8]) || 0, y: parseFloat(t[9]) || 0 };
        p.view.touched = true;
      }
      const m = t[10] || 'depth3d';
      if (m !== (p.mode || 'depth3d')) { p.mode = m; if (pel) applyPinMode(p, pel); }
    } else if (t[0] === 'rail') {
      Object.assign(p, { x: +t[2], y: +t[3], w: +t[4], h: +t[5] });
      if (t[1] !== p.rule && p.el) { p.rule = t[1]; p.tree = null; p.hist = []; railPinLoad(p, p.el); }
    } else {
      const [se, ee, de] = [+t[1], +t[2], +t[3]];
      if (se !== p.s || ee !== p.e || de !== p.d || t[4] !== p.rule) {
        Object.assign(p, {
          s: se, e: ee, d: de, rule: t[4],
          snip: S.doc.slice(se, Math.min(ee, se + 400)),
        });
        if (pel) pel.remove();  // header/snip/def all changed — rebuild, keeping geometry
      }
      if (t[9] !== undefined) p.gen = t[9];
      Object.assign(p, { x: +t[5], y: +t[6], w: +t[7], h: +t[8] || 0 });
    }
    if (pel) {
      pel.style.left = p.x + 'px';
      pel.style.top = p.y + 'px';
      if (p.w) pel.style.width = p.w + 'px';
      if (p.h) pel.style.height = p.h + 'px';
    }
  }
  renderPins();
}

async function pollPolicy() {
  try {
    const text = await (await fetch('/policy')).text();
    const P = {};
    for (const ln of text.split('\n')) {
      if (!ln.trim()) continue;
      const k = ln.slice(0, ln.indexOf(' '));
      P[k] = ln.slice(k.length + 1);
    }
    if (policySnap === null) {
      policySnap = P;  // boot already applied the whole record
    } else if (performance.now() - lastLocalPost > 2500) {
      const old = policySnap;
      const keys = new Set([...Object.keys(P), ...Object.keys(old)]);
      let pinDelta = false, any = false;
      for (const k of keys) {
        if (P[k] === old[k]) continue;
        any = true;
        if (k.startsWith('pin.')) pinDelta = true;
        else applyPolicyKey(k, P[k]);
      }
      if (pinDelta) syncPinsFromPolicy(P);
      if (any) { drawGraph(); ask(); }
      policySnap = P;
    }
    // inside the quiet window: keep the old snapshot — the delta re-diffs next tick
  } catch { /* the wire owns retries: next tick */ }
  setTimeout(pollPolicy, 2000);
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
