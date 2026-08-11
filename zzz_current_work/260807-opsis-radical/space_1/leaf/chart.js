/* opsis leaf — the derivation chart — density overview and depth lanes.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── chart facet: overview density + depth lanes ── */

// how the served band's tones look here. A drawing names a tone; what that
// tone IS belongs to the leaf, which is the only side that knows the dark.
const BAND = {
  band0: '#0e151d', band1: '#152230', band2: '#1d3143', band3: '#274257',
};

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
  // THE LANES ARE A DRAWING. Which frame sits in which row, how wide, is
  // the engine's own shape — it was being re-derived here every frame from
  // a list the leaf had already been handed. What stays is the tint, which
  // is the cursor's, and the marks that are not lanes at all.
  // where the window starts on screen: sx maps an offset to a pixel, so
  // the left edge is simply where the window's first character lands
  const pad = sx(at);
  const key = `clock:${pda ? 'pda' : 'earley'}:${Math.round(at)}:${win}`
    + `:${Math.round(w)}:${S.meta.generation}`;
  const said = drawings.get(key);
  if (!said) {
    loadDrawing(key, `&mode=${pda ? 'pda' : 'earley'}&from=${Math.round(at)}`
      + `&win=${win}&box=${Math.round(w - 2 * pad)}x${Math.round(y1 - lanesY - 8)}`,
      'clock');
  } else {
    cx.save();
    cx.translate(pad, clockHit.lanesY);
    for (const mark of said.marks) {
      const m = mark.split(' ');
      if (m[0] !== 'box') continue;
      const [bx, by, bw, bh] = [+m[1], +m[2], +m[3], +m[4]];
      const [s0, e0, index] = m[6].split(':').map(Number);
      const kept = m[5] === 'kept';
      const done = e0 <= T, live = !done && s0 < T;
      if (!kept) {
        cx.strokeStyle = 'rgba(224,96,96,0.55)';
        if (done) {
          cx.fillStyle = 'rgba(224,96,96,0.12)';
          cx.fillRect(bx, by, bw, bh);
        }
      } else if (done) {
        cx.fillStyle = pda ? withA('#8fa3b8', 0.20) : C.closed;
        cx.fillRect(bx, by, bw, bh);
        cx.strokeStyle = pda ? withA('#8fa3b8', 0.9) : C.cool;
      } else if (live) {
        cx.fillStyle = C.active;
        cx.fillRect(bx, by, bw, bh);
        cx.strokeStyle = C.warm;
      } else {
        cx.strokeStyle = pda ? withA('#8fa3b8', 0.35) : C.pending;
      }
      cx.strokeRect(bx + 0.5, by + 0.5, Math.max(bw - 1, 1.5), bh);
      const holds = pda ? clockData.frames[index] : clockData.hyp[index];
      if (clockHoverExt && holds === clockHoverExt) {
        cx.strokeStyle = C.ink;
        cx.strokeRect(bx - 1.5, by - 1.5, bw + 3, bh + 2);
      }
    }
    cx.restore();
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
  // how many characters one pixel of the overview stands for — the clock
  // band still needs it, and it went out with the coverage array it fed
  const step = Math.max(1, Math.floor(N / Math.max(1, w - 2 * pad)));
  // THE BAND IS A DRAWING: how much structure sits where is a property of
  // the reading, not something to sum over twelve thousand spans per frame.
  const bandKey = `band:${Math.round(w)}:${S.meta.generation}`;
  const band = drawings.get(bandKey);
  if (clock !== 'model' && clockReady()) {
    drawClockBand(cx, pad, bandH, step, ox, N, view);
  } else if (band) {
    cx.save();
    cx.translate(pad, 8);
    for (const mark of band.marks) {
      const m = mark.split(' ');
      if (m[0] !== 'box') continue;
      cx.fillStyle = BAND[m[5]] || shades[0];
      cx.fillRect(+m[1], +m[2], +m[3], +m[4]);
    }
    cx.restore();
  } else {
    loadDrawing(bandKey, `&box=${Math.round(w - 2 * pad)}x${bandH}`, 'band');
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
  // THE LANES ARE A DRAWING. Which span sits where, how wide, in which
  // lane — all of that is the reading's, addressed by the span it is. What
  // stays here is the window (the leaf chose it), the cursor (the leaf
  // moves it) and the tint that follows from the two.
  const key = `chart:${Math.round(at)}:${win}:${Math.round(w)}:${S.meta.generation}`;
  const lanes = drawings.get(key);
  if (!lanes) {
    loadDrawing(key, `&from=${Math.round(at)}&win=${win}`
      + `&box=${Math.round(w - 2 * pad)}x${Math.round(h - lanesY - 8)}`, 'chart');
  } else {
    cx.save();
    cx.translate(pad, lanesY);
    for (const mark of lanes.marks) {
      const m = mark.split(' ');
      if (m[0] !== 'box') continue;
      const [bx, by, bw, bh] = [+m[1], +m[2], +m[3], +m[4]];
      const [s0, e0, idx] = m[6].split(':').map(Number);
      const tone = m[5] === 'eps'
        ? (s0 <= T ? C.dimmer : C.pending)
        : (e0 <= T ? C.cool : (s0 < T ? C.warm : C.pending));
      if (e0 <= T && m[5] !== 'eps') { cx.fillStyle = C.closed; cx.fillRect(bx, by, bw, bh); }
      else if (s0 < T && m[5] !== 'eps') { cx.fillStyle = C.active; cx.fillRect(bx, by, bw, bh); }
      cx.strokeStyle = tone;
      cx.strokeRect(bx + 0.5, by + 0.5, Math.max(bw, 1), bh);
      if (idx === cur.sel || idx === cur.hover) {
        cx.strokeStyle = idx === cur.hover ? C.ink : C.warm;
        cx.strokeRect(bx - 1.5, by - 1.5, bw + 3, bh + 3);
      }
      if (markedRule() && S.ruleNames[S.spans[idx].r] === markedRule()) {
        cx.strokeStyle = C.violet;
        cx.strokeRect(bx - 1.5, by - 1.5, bw + 3, bh + 3);
      }
    }
    cx.restore();
  }
  const cxx = sx(Math.min(Math.max(T, at), at + win));
  cx.strokeStyle = C.warm;
  cx.beginPath(); cx.moveTo(cxx, lanesY - 6); cx.lineTo(cxx, h - 4); cx.stroke();
}
