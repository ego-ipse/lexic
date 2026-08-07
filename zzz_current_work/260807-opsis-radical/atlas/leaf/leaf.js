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
let cur = { t: 0, playing: false, sel: -1, hover: -1, rule: '', docSel: null, frontier: -1 };
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
  const probe = document.createElement('div');
  probe.className = 'ln';
  probe.innerHTML = '<span class="g">0</span><span class="t">' + 'M'.repeat(40) + '</span>';
  $('docBody').appendChild(probe);
  const t = probe.querySelector('.t').getBoundingClientRect();
  M = { charW: t.width / 40, gutterW: probe.querySelector('.g').getBoundingClientRect().width };
  probe.remove();
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

function drawOver() {
  const cx = $('over').getContext('2d');
  cx.clearRect(0, 0, 1e6, 1e6);
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
  if (cur.frontier >= 0) {
    const fl = lineOf(Math.min(cur.frontier, S.doc.length - 1));
    const fx = M.gutterW + (cur.frontier - S.lineStarts[fl]) * M.charW;
    const fy = PAD_TOP + fl * LH;
    cx.fillStyle = C.red;
    cx.shadowColor = C.red; cx.shadowBlur = 8;
    cx.fillRect(fx - 1, fy, 2, LH);
    cx.fillRect(fx - 4, fy + LH - 2, Math.max(M.charW + 8, 12), 2);
    cx.shadowBlur = 0;
  }
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
  const pitch = 5;
  const win = Math.floor((w - 2 * pad) / pitch);
  if (cur.t < view0 || cur.t > view0 + win * 0.72) view0 = Math.max(0, Math.min(cur.t - win * 0.6, N - win));
  cx.strokeStyle = C.warm;
  cx.strokeRect(ox(view0), 5, ox(Math.min(view0 + win, N)) - ox(view0), bandH + 6);
  const lanesY = bandH + 22;
  const laneH = Math.max(6, Math.floor((h - lanesY - 8) / (S.maxdepth + 1)));
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

function spanWords(i) {
  const s = S.spans[i];
  const f = S.fieldNames[s.f];
  return `${S.ruleNames[s.r]}${f ? ' · field ' + f : ''} · ${s.s.toLocaleString()}..${s.e.toLocaleString()} · d${s.d}`
    + (cur.docSel ? ' · E retypes the selection' : '');
}

function ask() { if (!needsDraw) { needsDraw = true; requestAnimationFrame(render); } }

let followT = -1;
function followCursor() {
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
  const doc = $('docBody');
  doc.addEventListener('mousemove', (e) => {
    const off = offsetAt(e);
    const hover = off < 0 ? -1 : deepestAt(off);
    if (hover !== cur.hover) { cur.hover = hover; ask(); }
  });
  doc.addEventListener('mouseleave', () => { cur.hover = -1; ask(); });
  doc.addEventListener('dblclick', (e) => {
    const off = offsetAt(e);
    if (off >= 0) { cur.playing = false; cur.t = off; ask(); }
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
  $('editInput').addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') submitEdit();
    if (e.key === 'Escape') { $('editbar').hidden = true; }
  });
}

function offsetAt(e) {
  const ln = e.target.closest('.ln');
  if (!ln) return -1;
  const t = ln.querySelector('.t').getBoundingClientRect();
  const col = Math.max(0, Math.round((e.clientX - t.left) / M.charW));
  const line = +ln.dataset.l;
  const len = (S.lineStarts[line + 1] ?? S.doc.length + 1) - 1 - S.lineStarts[line];
  return S.lineStarts[line] + Math.min(col, len);
}

function readSelection() {
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) { cur.docSel = null; return; }
  const within = (node) => $('docBody').contains(node.nodeType === 3 ? node.parentNode : node);
  if (!within(sel.anchorNode) || !within(sel.focusNode)) return;
  const offOf = (node, k) => {
    const ln = (node.nodeType === 3 ? node.parentNode : node).closest('.ln');
    return ln ? S.lineStarts[+ln.dataset.l] + k : -1;
  };
  const a = offOf(sel.anchorNode, sel.anchorOffset), b = offOf(sel.focusNode, sel.focusOffset);
  if (a < 0 || b < 0) return;
  cur.docSel = { lo: Math.min(a, b), hi: Math.max(a, b) };
  cur.sel = smallestOver(cur.docSel.lo, cur.docSel.hi);
  ask();
}

function onKey(e) {
  if (!$('editbar').hidden) return;
  if (e.key === ' ') { e.preventDefault(); cur.playing ? (cur.playing = false, ask()) : play(); }
  else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    cur.playing = false;
    cur.t = Math.max(0, Math.min(Math.floor(cur.t) + (e.key === 'ArrowRight' ? 1 : -1), S.doc.length));
    ask();
  } else if ((e.key === 'e' || e.key === 'E') && cur.docSel) {
    $('banner').hidden = true;
    $('editSpan').textContent = `${cur.docSel.lo.toLocaleString()}..${cur.docSel.hi.toLocaleString()}`;
    $('editInput').value = S.doc.slice(cur.docSel.lo, cur.docSel.hi);
    $('editbar').hidden = false;
    $('editInput').focus();
  } else if (e.key === 'Escape') { cur.sel = -1; cur.rule = ''; cur.frontier = -1; $('banner').hidden = true; ask(); }
}

async function submitEdit() {
  const { lo, hi } = cur.docSel;
  $('editbar').hidden = true;
  await applyEdit(lo, hi, $('editInput').value);
}

async function applyEdit(lo, hi, value) {
  const resp = await (await fetch('/edit', { method: 'POST', body: `${lo} ${hi}\n${value}` })).text();
  const banner = $('banner');
  banner.hidden = false;
  const [head] = resp.split('\n', 1);
  if (head.startsWith('ok')) {
    banner.className = 'ok';
    cur.frontier = -1;
    await boot(true);
    banner.textContent = `generation ${S.meta.generation} — the document was re-read in ${head.slice(3)}s; every facet re-derived`;
  } else {
    banner.className = 'refuse';
    const words = resp.slice(head.length + 1);
    const pos = parseInt(head.split(' ')[1], 10);
    cur.frontier = Number.isFinite(pos) ? pos : -1;
    if (cur.frontier >= 0) {
      banner.textContent = `${words} — frontier at char ${cur.frontier.toLocaleString()}; the red mark is the deepest verified position`;
      cur.playing = false; cur.t = cur.frontier; cur.follow = true;
    } else {
      banner.textContent = `${words} — frontier unmeasured on this route (the engine's refusal carries no position; recorded lexic gap)`;
    }
    ask();
  }
}

/* ── boot ── */

async function boot(keep) {
  const text = await (await fetch('/scene')).text();
  const t0 = keep ? Math.min(cur.t, 1e12) : 0;
  S = parseScene(text);
  cur.sel = -1; cur.hover = -1; cur.docSel = null;
  buildCode($('docBody'), S.doc.split('\n'), true);
  buildCode($('grammarBody'), S.readerLines, false);
  if (!M) measure();
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

(async () => {
  await boot(false);
  wire();
  const q = new URLSearchParams(location.search);
  if (q.has('t')) { cur.t = Math.min(+q.get('t'), S.doc.length); cur.follow = true; ask(); }
  if (q.has('sel')) { cur.sel = deepestAt(+q.get('sel')); ask(); }
  if (q.has('rule')) { cur.rule = q.get('rule'); ask(); }
  if (q.has('break')) { const off = +q.get('break'); applyEdit(off, off + 1, '\u00a7'); }
  else setTimeout(play, 600);
})();
