/* opsis leaf — the derivation chart — density overview and depth lanes.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

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
      else if (ln.startsWith('pda_words ')) data.pdaWords = ln.slice(10);
      else if (ln.startsWith('dropped ')) data.dropped = +ln.slice(8);
      else if (ln.startsWith('#PDAFRAMES')) section = 'f';
      else if (ln.startsWith('#PDANAMES')) section = 'fn';
      else if (ln.startsWith('#EVENTS')) section = 't';
      else if (ln.startsWith('#EARLEYNAMES')) section = 'hn';
      else if (ln.startsWith('#EARLEY')) section = 'h';
      else if (section === 'f') {
        const [a, b, c, d, e, f2] = ln.split(' ');
        data.frames.push({ s: +a, e: +b, d: +c, n: +d, cid: +e, ok: f2 === undefined ? 1 : +f2 });
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

function truncLine(cx, text, maxW) {
  let line = text;
  while (line.length > 8 && cx.measureText(line).width > maxW) {
    line = line.slice(0, -8) + '…';
  }
  return line;
}

function drawLegend(cx, w, h, text) {
  cx.fillStyle = '#66707f';
  cx.font = '10px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
  cx.fillText(truncLine(cx, text, w - 20), 12, h - 5);
}

function withA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function clockBandTex() {
  // per-char textures, built once per clock load: the band's raw material
  if (clockData.tex) return clockData.tex;
  const N = S.doc.length;
  const depth = new Int16Array(N + 2);
  for (const f of clockData.frames) { depth[f.s]++; depth[Math.max(f.e, f.s + 1)]--; }
  let run = 0, top = 1;
  for (let i = 0; i <= N; i++) { run += depth[i]; depth[i] = run; top = Math.max(top, run); }
  const live = new Int16Array(N + 2), dead = new Int16Array(N + 2);
  for (const hh of clockData.hyp) {
    const arr = hh.c ? live : dead;
    arr[hh.s]++; arr[Math.max(hh.e, hh.s + 1)]--;
  }
  let lr = 0, dr = 0, ltop = 1;
  const liveC = new Int16Array(N + 1), deadC = new Int16Array(N + 1);
  for (let i = 0; i <= N; i++) {
    lr += live[i]; dr += dead[i];
    liveC[i] = lr; deadC[i] = dr; ltop = Math.max(ltop, lr);
  }
  const decided = new Uint8Array(N + 1);
  for (const ev of clockData.events) if (ev.pos <= N) decided[ev.pos] = 1;
  clockData.tex = { depth, top, liveC, deadC, ltop, decided };
  return clockData.tex;
}

function drawClockBand(cx, pad, bandH, step, ox, N, view = chartMain) {
  const tex = clockBandTex();
  const pda = chartClockOf(view) === 'pda';
  for (let off = 0; off < N; off += step) {
    let v = 0, mark = 0, dead = 0;
    for (let k = off; k < Math.min(off + step, N); k++) {
      v = Math.max(v, pda ? tex.depth[k] : tex.liveC[k]);
      if (pda && tex.decided[k]) mark = 1;
      if (!pda) dead = Math.max(dead, tex.deadC[k]);
    }
    const x = ox(off), bw = Math.max(1, ox(off + step) - x);
    if (pda) {
      // the machine's stack depth is the walk's texture; warm where it decided
      cx.fillStyle = mark ? '#e2a65c'
        : v === 0 ? '#12161f'
        : withA('#6fc3c9', 0.10 + 0.55 * Math.min(1, v / tex.top));
    } else {
      cx.fillStyle = dead && !v ? withA('#e06060', 0.4)
        : withA('#d98cf5', 0.08 + 0.6 * Math.min(1, v / tex.ltop));
      if (dead && v) cx.fillStyle = withA('#c77b9b', 0.25 + 0.45 * Math.min(1, v / tex.ltop));
    }
    cx.fillRect(x, 8, bw, bandH);
  }
}

function drawClockLanes(cx, w, h, lanesY, pitch, sx, view = chartMain) {
  const pda = chartClockOf(view) === 'pda';
  const T = chartAt(view), at = view.hit ? view.hit.at : view0;
  if (pda && !autoData) fetchAutomaton();
  if (pda && !clockData.frames.length) {
    cx.fillStyle = C.dim;
    cx.font = '11px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
    cx.fillText(truncLine(cx, 'the PDA never ran' + (clockData.pdaWords ? ' — ' + clockData.pdaWords : ''), w - 24), 12, lanesY + 18);
    cx.fillText(truncLine(cx, 'this reading came from Earley' + (S.meta.resolver === '1' ? ' + the supplied resolver' : '') + ' — the earley clock tells its time', w - 24), 12, lanesY + 34);
    return;
  }
  const list = pda ? clockData.frames : clockData.hyp;
  const rows = pda ? clockData.frameRows : clockData.hypRows;
  const y1 = h - 18;
  const laneH = Math.max(2, Math.min(16, Math.floor((y1 - lanesY - 4) / Math.max(1, rows))));
  const win = (view.hit || S.chartHit).win;
  clockHit = { lanesY: lanesY + 4, laneH, pda };
  const abandoned = 'rgba(224,96,96,0.55)';
  const abandonedFill = 'rgba(224,96,96,0.16)';
  for (const f of list) {
    if (f.e <= at || f.s >= at + win) continue;
    const row = pda ? f.d : f.row;
    const y = clockHit.lanesY + row * laneH;
    if (y + laneH > y1) continue;
    const x1 = sx(Math.max(f.s, at));
    const x2 = Math.max(sx(Math.min(f.e, at + win)), x1 + 1.5);
    const done = f.e <= T, live = !done && f.s < T;
    if (pda) {
      const cmode = f.cid >= 0 && autoData && autoData.clones[f.cid] ? autoData.clones[f.cid].mode : null;
      const base = cmode ? (AUTO_INK[cmode] || '#8fa3b8') : '#8fa3b8';
      if (!f.ok) {
        // an attempt sub-run pushed it, the rollback took it away — the same
        // fate register as Earley's abandoned hypotheses
        cx.strokeStyle = 'rgba(224,96,96,0.55)';
        if (done) { cx.fillStyle = 'rgba(224,96,96,0.12)'; cx.fillRect(x1, y, x2 - x1, laneH - 1); }
        cx.strokeRect(x1 + 0.5, y + 0.5, Math.max(x2 - x1 - 1, 1.5), laneH - 1);
        continue;
      }
      if (done) { cx.fillStyle = withA(base, 0.20); cx.fillRect(x1, y, x2 - x1, laneH - 1); cx.strokeStyle = withA(base, 0.9); }
      else if (live) {
        cx.fillStyle = C.active;
        cx.fillRect(x1, y, sx(Math.min(T, at + win)) - x1, laneH - 1);
        cx.strokeStyle = C.warm;
      } else cx.strokeStyle = withA(base, 0.35);
    } else if (f.c) {
      if (done) { cx.fillStyle = C.closed; cx.fillRect(x1, y, x2 - x1, laneH - 1); }
      cx.strokeStyle = done ? C.cool : C.pending;
    } else {
      if (done) { cx.fillStyle = abandonedFill; cx.fillRect(x1, y, x2 - x1, laneH - 1); }
      cx.strokeStyle = abandoned;
    }
    cx.strokeRect(x1 + 0.5, y + 0.5, Math.max(x2 - x1 - 1, 1.5), laneH - 1);
    // a frame wide enough to read says WHAT IT IS. Boxes alone made the two
    // clocks look like the same picture twice, and made a machine of 126
    // distinct clones read as one rule entered over and over.
    const said = pda ? clockData.fnames[f.n] : clockData.hnames[f.n];
    if (said && x2 - x1 > 34 && laneH >= 9) {
      cx.save();
      cx.beginPath();
      cx.rect(x1 + 1, y, x2 - x1 - 2, laneH - 1);
      cx.clip();
      cx.fillStyle = f.ok === 0 || (!pda && !f.c) ? 'rgba(224,96,96,0.85)' : C.dim;
      cx.font = `${Math.min(10, laneH - 2)}px ` + getComputedStyle(
        document.documentElement).getPropertyValue('--mono');
      cx.fillText(said, x1 + 3, y + laneH - 3);
      cx.restore();
    }
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
      if (ev.pos < at || ev.pos > at + win) continue;
      cx.fillRect(sx(ev.pos), lanesY - 2, Math.max(2, pitch / 2), 4);
    }
  }
  if (pda && clockData.pdaEnd >= 0 && clockData.pdaEnd >= at && clockData.pdaEnd <= at + win) {
    cx.strokeStyle = C.red || '#e06060';
    cx.beginPath(); cx.moveTo(sx(clockData.pdaEnd), lanesY); cx.lineTo(sx(clockData.pdaEnd), y1); cx.stroke();
  }
  const legend = pda
    ? `frames by clone mode (grey seq · cool dispatch · violet value_str · amber alt) · red: rolled back · warm ticks: decisions${clockData.pdaEnd >= 0 ? ' · red line: the fast road stops' : ''}`
    : `hypotheses (rule, origin) · red: abandoned · ${clockData.hypRows} live at the widest`
      + (clockData.dropped ? ` · ${clockData.dropped.toLocaleString()} not shipped` : '');
  drawLegend(cx, w, h, legend);
}

// The chart drawn for the facet — the view every gesture edits. A second
// chart is a second one of these, with its own window and its own moment,
// which is what makes a clone a view rather than a picture of a view.
const chartMain = { cv: 'chartCv', zoom: null, clock: null, t: null, hit: null };

function chartAt(view) { return view.t === null ? cur.t : view.t; }
function chartZoomOf(view) { return view.zoom === null ? chartZoom : view.zoom; }
function chartClockOf(view) { return view.clock === null ? chartClock : view.clock; }

function drawChart(view = chartMain) {
  const cv = typeof view.cv === 'string' ? $(view.cv) : view.cv;
  if (!cv || !S) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return;
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const cx = cv.getContext('2d');
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  const pad = 10, bandH = 26, N = S.doc.length;
  const T = chartAt(view), zoom = chartZoomOf(view), clock = chartClockOf(view);
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
  if (clock !== 'model' && clockReady()) {
    drawClockBand(cx, pad, bandH, step, ox, N, view);
  } else {
    for (let off = 0; off < N; off += step) {
      let m = 0;
      for (let k = off; k < Math.min(off + step, N); k++) m = Math.max(m, S.cov[k]);
      cx.fillStyle = shades[Math.min(3, Math.floor((m * 4) / (S.covTop + 1)))];
      cx.fillRect(ox(off), 8, Math.max(1, ox(off + step) - ox(off)), bandH);
    }
  }
  // a small document fills the width; a large one gets a 5px-per-char window
  const base = N * 5 < (w - 2 * pad) ? Math.min(12, Math.floor((w - 2 * pad) / Math.max(1, N))) : 5;
  const pitch = Math.max(0.5, base * zoom);
  const win = Math.max(8, Math.floor((w - 2 * pad) / pitch));
  // each view keeps its own window into the text; the facet's is the shared
  // one, so scrubbing still moves what you are looking at
  let at = view === chartMain ? view0 : (view.at || 0);
  at = Math.max(0, Math.min(at, Math.max(0, N - win)));
  if (T < at || T > at + win * 0.72) {
    at = Math.max(0, Math.min(T - win * 0.6, Math.max(0, N - win)));
  }
  if (view === chartMain) view0 = at; else view.at = at;
  cx.strokeStyle = C.warm;
  cx.strokeRect(ox(at), 5, ox(Math.min(at + win, N)) - ox(at), bandH + 6);
  const lanesY = bandH + 22;
  const laneH = Math.max(6, Math.min(22, Math.floor((h - lanesY - 8) / (S.maxdepth + 1))));
  const sx = (off) => pad + (off - at) * pitch;
  const hit = { pad, bandH, lanesY, laneH, pitch, win, ox, at };
  view.hit = hit;
  if (view === chartMain) S.chartHit = hit;
  if (clock !== 'model') {
    if (!clockReady()) {
      loadClock();
      cx.fillStyle = C.dim;
      cx.fillText(`the ${clock} clock is running…`, 12, lanesY + 14);
    } else {
      drawClockLanes(cx, w, h, lanesY, pitch, sx, view);
    }
    const cxx0 = sx(Math.min(Math.max(T, at), at + win));
    cx.strokeStyle = C.warm;
    cx.beginPath(); cx.moveTo(cxx0, lanesY - 6); cx.lineTo(cxx0, h - 4); cx.stroke();
    return;
  }
  // one pass, carrying the index: `indexOf` inside this loop was a linear
  // scan of 12k spans per drawn span — quadratic, on every frame
  S.spans.forEach((s, idx) => {
    if (s.e <= at || s.s >= at + win) return;
    const x1 = sx(Math.max(s.s, at)), x2 = sx(Math.min(s.e, at + win));
    const y = lanesY + s.d * laneH;
    if (s.e === s.s) {
      // an ε match holds no text: drawing it as a box the width of two
      // characters puts 1,400 objects on screen that the document does not
      // contain. It is a mark AT a place, so it is drawn as one.
      cx.strokeStyle = s.s <= T ? C.dimmer : C.pending;
      cx.beginPath();
      cx.moveTo(x1 + 0.5, y + 1);
      cx.lineTo(x1 + 0.5, y + laneH - 3);
      cx.stroke();
      if (idx === cur.hover || idx === cur.sel) {
        cx.strokeStyle = idx === cur.hover ? C.ink : C.warm;
        cx.strokeRect(x1 - 2.5, y - 1.5, 5, laneH + 1);
      }
      return;
    }
    if (s.e <= T) { cx.fillStyle = C.closed; cx.fillRect(x1, y, x2 - x1, laneH - 2); cx.strokeStyle = C.cool; }
    else if (s.s < T) {
      cx.fillStyle = C.active; cx.fillRect(x1, y, sx(Math.min(T, at + win)) - x1, laneH - 2);
      cx.strokeStyle = C.warm;
    } else cx.strokeStyle = C.pending;
    cx.strokeRect(x1 + 0.5, y + 0.5, Math.max(x2 - x1 - 1, 2), laneH - 2);
    if (idx === cur.sel || idx === cur.hover) {
      // the hand's mark is the BRIGHT one: it is where you are pointing
      cx.strokeStyle = idx === cur.hover ? C.ink : C.warm;
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 1);
    }
    if (markedRule() && S.ruleNames[s.r] === markedRule()) {
      cx.strokeStyle = C.violet;
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 1);
    }
  });
  const cxx = sx(Math.min(Math.max(T, at), at + win));
  cx.strokeStyle = C.warm;
  cx.beginPath(); cx.moveTo(cxx, lanesY - 6); cx.lineTo(cxx, h - 4); cx.stroke();
}
