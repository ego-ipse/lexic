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
  const clones = [], names = [], edges = [], places = [];
  let section = '';
  for (const ln of text.split('\n')) {
    if (ln.startsWith('#ACLONES')) section = 'c';
    else if (ln.startsWith('#ANAMES')) section = 'n';
    else if (ln.startsWith('#APLACES')) section = 'p';
    else if (ln.startsWith('#AEDGES')) section = 'e';
    else if (section === 'c') {
      const [ni, mode, flags, depth] = ln.split(' ');
      clones.push({ n: +ni, mode, flags, depth: +depth });
    } else if (section === 'p') {
      const [x, y] = ln.split(' ');
      places.push({ x: +x, y: +y });
    } else if (section === 'n') names.push(ln);
    else if (section === 'e') {
      const [a, b] = ln.split(' ');
      edges.push([+a, +b]);
    }
  }
  const levels = new Map();
  clones.forEach((c, i) => {
    c.name = names[c.n];
    c.at = places[i] || { x: 0, y: 0 };
    const d = c.depth < 0 ? 0 : c.depth;
    if (!levels.has(d)) levels.set(d, []);
    levels.get(d).push(c);
  });
  autoData = { clones, edges, maxDepth: Math.max(...levels.keys()) };
  drawGraph();
}

const AUTO_INK = { dispatch: '#6fc3c9', alt: '#e2a65c', seq: '#8fa3b8', value_str: '#d98cf5', group: '#66707f' };

function autoPos(c) {
  // the machine says where its clones sit — a column per depth, a seat per
  // clone. Deriving it here made the machine's shape a fact about the leaf.
  return c.at || { x: 0, y: 0 };
}

function drawRailPin(p, el) {
  // the pinned railroad is the SAME drawing the rails view paints, asked
  // for one rule. Everything it used to compute — measure, lay out, stroke
  // every line — was a second copy of what the reading already says.
  const body = el.querySelector('.railbody');
  const cv = el.querySelector('canvas');
  const said = drawings.get(`rail:${p.rule}`);
  if (!said) { loadDrawing(`rail:${p.rule}`, `&name=${encodeURIComponent(p.rule)}`, 'rail'); return; }
  const w = body.clientWidth, h = body.clientHeight;
  if (!w || !h) return;
  const scale = Math.min(1.4, Math.max(0.4,
    Math.min((w - 16) / Math.max(1, said.w), (h - 16) / Math.max(1, said.h))));
  p.scale = scale;
  paint(cv, said, { x: 8, y: 8 }, scale);
  p.painted = said;
}

async function railPinLoad(p, el) {
  const body = el.querySelector('.railbody');
  const cv = el.querySelector('canvas');
  const said = await loadDrawing(`rail:${p.rule}`,
    `&name=${encodeURIComponent(p.rule)}`, 'rail');
  if (!said || !said.marks.length) { body.textContent = 'no such rule ' + p.rule; return; }
  p.tree = said;
  if (!p.w) {
    p.w = Math.min(said.w + 52, Math.floor(window.innerWidth * 0.72));
    p.h = Math.min(said.h + 58, Math.floor(window.innerHeight * 0.72));
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
    loadPlaces(gView, true);   // a different view is a different layout
    drawGraph();
  });
  for (const k of ['levelstep', 'ringscale', 'flatten', 'labelscale']) {
    $('gt-' + k).addEventListener('input', (e) => {
      gTune[k] = parseFloat(e.target.value);
      // a slider changes the LAYOUT, and the layout is derived: the leaf
      // reports what was dragged and asks for the places again. Only the
      // label scale is the leaf's, because it is type size, not a position.
      if (k === 'labelscale') {
        document.documentElement.style.setProperty('--glabel', gTune.labelscale);
        drawGraph();
      } else {
        postPolicy('graph.' + k, gTune[k]);
        loadPlaces(gView, true);
      }
      postPolicyDebounced('graph.' + k, gTune[k]);
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
