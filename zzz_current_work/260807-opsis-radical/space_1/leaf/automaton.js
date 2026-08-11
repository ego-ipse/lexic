/* opsis leaf — the automaton — the compiled machine, walk-lit.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── the automaton view — the compiled machine itself, walk-lit at t ── */

let autoData = null;
let autoLoading = false;

let verdictMap = null;
let verdictLoading = false;

async function fetchVerdicts() {
  if (verdictMap || verdictLoading) return;
  verdictLoading = true;
  const text = await (await fetch('/verdicts')).text();
  verdictMap = new Map();
  const lines = text.split('\n').slice(1);
  let i = 0;
  while (i < lines.length) {
    const m = lines[i].match(/^(\S+) (\d+) (.*)$/);
    i++;
    if (!m) continue;
    const notes = lines.slice(i, i + +m[2]);
    i += +m[2];
    verdictMap.set(m[3], { cls: m[1], notes });
  }
  decorateVerdicts();
}

function decorateVerdicts() {
  if (!verdictMap) return;
  document.querySelectorAll('#grammarBody .vbadge').forEach((el) => el.remove());
  for (const def of S.ruledefs) {
    const v = verdictMap.get(def.name);
    if (!v) continue;
    const ln = document.querySelector(`#grammarBody .ln[data-l="${def.a}"]`);
    if (!ln) continue;
    const badge = document.createElement('span');
    badge.className = 'vbadge v-' + v.cls;
    badge.textContent = v.cls;
    badge.title = v.notes.join('\n') || v.cls;
    ln.appendChild(badge);
  }
}

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
  v.chips.style.display = 'none';  // canvas-only view: stale chips must not overlay
  if (!autoData) { fetchAutomaton(); return; }
  if (!autoData.clones.length) {
    const dpr0 = Math.min(window.devicePixelRatio || 1, 2);
    if (cv.width !== w * dpr0) { cv.width = w * dpr0; cv.height = h * dpr0; }
    const cx0 = cv.getContext('2d');
    cx0.setTransform(dpr0, 0, 0, dpr0, 0, 0);
    cx0.clearRect(0, 0, w, h);
    cx0.fillStyle = '#66707f';
    cx0.font = '11px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
    cx0.fillText(truncLine(cx0, 'no machine — the start rule is an island; the whole document is an Earley window.', w - 28), 14, h - 40);
    cx0.fillText(truncLine(cx0, "the earley clock tells this subject's time; the rule views (flat / rails) still apply.", w - 28), 14, h - 22);
    return;
  }
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
  if (!clockReady()) loadClock();
  const lit = clockReady() && clockData.frames.length > 0;
  if (lit) {
    for (const f of clockData.frames) {
      if (f.cid < 0 || !f.ok) continue;
      if (f.s <= cur.t && cur.t < f.e) inNow.add(f.cid);
      else if (f.e <= cur.t) visited.add(f.cid);
    }
  }
  cx.lineWidth = 1 / k;
  for (const [a, b] of autoData.edges) {
    // an edge whose ends are not both here is not drawable. It should never
    // arrive — but a bad index must not be able to stop time.
    if (!autoData.clones[a] || !autoData.clones[b]) continue;
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
  const litWord = lit ? ` · warm = the stack at t (${inNow.size} in)` : '';
  drawLegend(cx, w, h,
    `the machine — ${autoData.clones.length} clones · ■ seq · ● dispatch · violet value_str · warm ring: attempt · violet box: gated${litWord}`);
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

function setClock(value) {
  chartClock = value || 'model';
  $('cclock').value = chartClock;
  document.body.classList.toggle('clock-pda', chartClock === 'pda');
}

function wireClockSelect() {
  $('cclock').addEventListener('change', () => {
    setClock($('cclock').value);
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
  let drag = null;
  const seamAt = (e) => {
    const g = $(GRID).getBoundingClientRect();
    if (e.clientY <= g.top) return null;
    const px = e.clientX - g.left, py = e.clientY - g.top;
    return seamEdges.find((sm) => sm.axis === 'x'
      ? Math.abs(px - sm.at) <= 7 && py >= sm.from && py <= sm.to
      : Math.abs(py - sm.at) <= 7 && px >= sm.from && px <= sm.to) || null;
  };
  window.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.pin') || e.target.closest('#pinchip')) return;
    const sm = seamAt(e);
    if (sm) {
      drag = sm;
      e.preventDefault();
      document.body.style.cursor = sm.axis === 'x' ? 'col-resize' : 'row-resize';
    }
  }, true);
  window.addEventListener('pointermove', (e) => {
    if (!drag) {
      if (e.buttons) return;
      const sm = seamAt(e);
      document.body.style.cursor = sm ? (sm.axis === 'x' ? 'col-resize' : 'row-resize') : '';
      return;
    }
    const g = $(GRID).getBoundingClientRect();
    const p = drag.axis === 'x' ? e.clientX - g.left : e.clientY - g.top;
    drag.real[1] = Math.max(0.06, Math.min(0.94, (p - drag.base) / drag.size));
    layoutFacets();
    saveArrangement();
    ask();
  });
  window.addEventListener('pointerup', () => {
    if (drag) {
      drag = null;
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
