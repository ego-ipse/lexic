/* The derivation — text is the time axis. Three clocks over one
   coordinate: the model's spans, the PDA's frames, Earley's hypotheses.
   Carved out because it is the surface with the most failure modes and
   the most drawing per frame, and it shares only the cursors. */

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
    // A LANE IS A RULE. Greedy packing put a hypothesis in whatever slot was
    // free, so its height meant nothing and the chart was noise by
    // construction — the PDA clock reads because its row is stack depth.
    // Here the row is the rule being hypothesised, so a band of ink says
    // WHICH rule the engine was entertaining across that stretch of text,
    // and the rules are ordered by where they first appear.
    const laneOf = new Map();
    for (const hh of data.hyp) {
      hh.name = data.hnames[hh.n];
      if (!laneOf.has(hh.n)) laneOf.set(hh.n, laneOf.size);
      hh.row = laneOf.get(hh.n);
    }
    data.hypRows = Math.max(1, laneOf.size);
    data.hypLanes = [...laneOf.keys()].map((n) => data.hnames[n]);
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

function drawClockBand(cx, pad, bandH, step, ox, N) {
  const tex = clockBandTex();
  const pda = chartClock === 'pda';
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

function drawClockLanes(cx, w, h, lanesY, pitch, sx) {
  const pda = chartClock === 'pda';
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
    // a frame that merely SPANS the window is context, not an event: drawn
    // as a hairline it stops a handful of enclosing frames from reading as a
    // wall, and what opened or closed here stays visible
    if (f.s < view0 && f.e > view0 + win) {
      cx.strokeStyle = f.ok === 0 ? abandoned : 'rgba(143,163,184,0.22)';
      cx.beginPath();
      cx.moveTo(x1, y + (laneH - 1) / 2);
      cx.lineTo(x2, y + (laneH - 1) / 2);
      cx.stroke();
      continue;
    }
    const done = f.e <= cur.t, live = !done && f.s < cur.t;
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
        cx.fillRect(x1, y, sx(Math.min(cur.t, view0 + win)) - x1, laneH - 1);
        cx.strokeStyle = C.warm;
      } else cx.strokeStyle = withA(base, 0.35);
    } else if (f.c) {
      // COMPLETED hypotheses are the events worth seeing; filling every one
      // turns a thousand live hypotheses into a solid block that says only
      // "many". Fill what completed, outline what is still standing.
      if (done) { cx.fillStyle = C.closed; cx.fillRect(x1, y, x2 - x1, laneH - 1); }
      cx.strokeStyle = done ? C.cool : withA(C.pending, 0.45);
    } else {
      if (done) { cx.fillStyle = abandonedFill; cx.fillRect(x1, y, x2 - x1, laneH - 1); }
      cx.strokeStyle = withA(abandoned, 0.5);
    }
    if (pda || f.c || x2 - x1 > 2) {
      cx.strokeRect(x1 + 0.5, y + 0.5, Math.max(x2 - x1 - 1, 1.5), laneH - 1);
    } else {
      // a hypothesis narrower than a couple of pixels reads as a tick, not a
      // box: drawn as a box it is pure ink, and ink is what buried the chart
      cx.beginPath();
      cx.moveTo(x1 + 0.5, y + 0.5);
      cx.lineTo(x1 + 0.5, y + laneH - 1);
      cx.stroke();
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
      if (ev.pos < view0 || ev.pos > view0 + win) continue;
      cx.fillRect(sx(ev.pos), lanesY - 2, Math.max(2, pitch / 2), 4);
    }
  }
  if (pda && clockData.pdaEnd >= 0 && clockData.pdaEnd >= view0 && clockData.pdaEnd <= view0 + win) {
    cx.strokeStyle = C.red || '#e06060';
    cx.beginPath(); cx.moveTo(sx(clockData.pdaEnd), lanesY); cx.lineTo(sx(clockData.pdaEnd), y1); cx.stroke();
  }
  const legend = pda
    ? `frames by clone mode (grey seq · cool dispatch · violet value_str · amber alt) · red: rolled back · warm ticks: decisions${clockData.pdaEnd >= 0 ? ' · red line: the fast road stops' : ''}`
    : `one lane per rule · ${clockData.hypRows} rules hypothesised · red: abandoned`
      + (clockData.dropped ? ` · ${clockData.dropped.toLocaleString()} not shipped` : '');
  drawLegend(cx, w, h, legend);
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
  if (chartClock !== 'model' && clockReady()) {
    drawClockBand(cx, pad, bandH, step, ox, N);
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
  if (!S.passthrough) {
    // an arm that covers exactly the text its parent covers adds a second
    // identical bar and no information: 358 of them in the json reading.
    // The occurrence is real and stays in the spine; only the ink changes.
    S.passthrough = new Set();
    const openAt = [];
    S.spans.forEach((s, i) => {
      openAt[s.d] = i;
      const up = s.d > 0 ? S.spans[openAt[s.d - 1]] : null;
      if (up && up.s === s.s && up.e === s.e) S.passthrough.add(i);
    });
  }
  S.spans.forEach((s, at) => {
    if (s.e <= view0 || s.s >= view0 + win) return;
    const x1 = sx(Math.max(s.s, view0)), x2 = sx(Math.min(s.e, view0 + win));
    const y = lanesY + s.d * laneH;
    if (S.passthrough.has(at)) {
      cx.strokeStyle = 'rgba(111,195,201,0.30)';
      cx.beginPath();
      cx.moveTo(x1, y + (laneH - 2) / 2);
      cx.lineTo(x2, y + (laneH - 2) / 2);
      cx.stroke();
      return;
    }
    if (s.e <= cur.t) { cx.fillStyle = C.closed; cx.fillRect(x1, y, x2 - x1, laneH - 2); cx.strokeStyle = C.cool; }
    else if (s.s < cur.t) {
      cx.fillStyle = C.active; cx.fillRect(x1, y, sx(Math.min(cur.t, view0 + win)) - x1, laneH - 2);
      cx.strokeStyle = C.warm;
    } else cx.strokeStyle = C.pending;
    cx.strokeRect(x1 + 0.5, y + 0.5, Math.max(x2 - x1 - 1, 2), laneH - 2);
    const idx = at;
    if (idx === cur.sel || idx === cur.hover) {
      cx.strokeStyle = idx === cur.sel ? C.warm : C.dim;
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 1);
    }
    if (markedRule() && S.ruleNames[s.r] === markedRule()) {
      cx.strokeStyle = C.violet;
      cx.strokeRect(x1 - 1.5, y - 1.5, x2 - x1 + 3, laneH + 1);
    }
  });
  const cxx = sx(Math.min(Math.max(cur.t, view0), view0 + win));
  cx.strokeStyle = C.warm;
  cx.beginPath(); cx.moveTo(cxx, lanesY - 6); cx.lineTo(cxx, h - 4); cx.stroke();
}

