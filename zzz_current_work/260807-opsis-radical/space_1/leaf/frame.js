/* opsis leaf — the frame, and policy as the leaf's memory.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

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
  drawTwins();  // a cloned surface is the same surface, drawn again
  const state = cur.playing ? 'playing' : (cur.t >= S.doc.length ? 'complete' : 'paused');
  const line = lineOf(Math.min(Math.floor(cur.t), S.doc.length - 1)) + 1;
  $('pos').textContent =
    `char ${Math.floor(Math.min(cur.t, S.doc.length)).toLocaleString()} / ${S.doc.length.toLocaleString()}`
    + ` · line ${line.toLocaleString()} / ${S.lineStarts.length.toLocaleString()} · ${state}`
    + (speed !== 1 ? ` · speed ${speedWord()}` : '') + ` · gen ${S.meta.generation}`;
  $('tb-play').textContent = cur.playing ? '⏸' : '▶';
  $('tb-speed').textContent = speedWord();
  // the HAND wins. A selection persists, a hover is where you are pointing
  // right now — reading out the selection while the pointer is somewhere
  // else is the instrument describing a different thing than it highlights.
  const focus = cur.hover >= 0 ? cur.hover : cur.sel;
  let words = focus < 0 ? (cur.rule ? `rule ${cur.rule} — its spans outlined violet` : '')
    : (cur.hover >= 0 ? 'under the hand · ' : 'selected · ') + spanWords(focus);
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

function opensFor(P) {
  // "graph:?graph=1&gpin=1 machine:?place=machine" — the address is the
  // instrument's OWN query, so opening a surface is going where it lives
  const out = {};
  for (const pair of (P['opens'] || '').split(' ').filter(Boolean)) {
    const cut = pair.indexOf(':');
    if (cut > 0) out[pair.slice(0, cut)] = pair.slice(cut + 1);
  }
  return out;
}

function openAddress(address) {
  // honour what the surface asked for. Sending every ⧉ to the graph was the
  // instrument answering a question with someone else's answer.
  if (!address || address === 'none-yet') return;
  const q = new URLSearchParams(address.replace(/^\?/, ''));
  if (q.has('place')) { openPlace(q.get('place')); return; }
  if (q.has('graph')) {
    if (!graphOn) setGraph(true, true);
    if (q.has('gpin') && typeof graphPin === 'function') graphPin();
  }
}

function applyPolicy() {
  const P = S.policy || {};
  if (P['speed']) speed = parseFloat(P['speed']) || speed;
  if (P['doc.zoom']) { docZoom = parseFloat(P['doc.zoom']) || 1; applyDocZoom(); }
  if (P['chart.zoom']) chartZoom = parseFloat(P['chart.zoom']) || 1;
  if (P['chart.clock']) setClock(P['chart.clock']);
  if (P['spine.zoom']) { spineZoom = parseFloat(P['spine.zoom']) || 1; applySpineZoom(); }
  if (P['graph.view']) gView = P['graph.view'];
  for (const k of ['levelstep', 'ringscale', 'flatten', 'labelscale']) {
    if (P['graph.' + k]) gTune[k] = parseFloat(P['graph.' + k]);
  }
  document.documentElement.style.setProperty('--glabel', gTune.labelscale);
  for (const which of ['reader', 'right', 'top']) {
    if (P['arrange.' + which]) setShare(which, parseFloat(P['arrange.' + which]), false);
  }
  for (const name of FACETS) {
    if (P['facet.' + name]) facetOn[name] = P['facet.' + name] !== 'off';
  }
  // whether the relations are on is the facet's own state, and the graph
  // must be BUILT before it can be drawn into the column it was given
  graphOn = facetOn['graph'] !== false;
  if (graphOn && !gNodes && S.edges) buildGraph();
  if (P['arrange.tree']) {
    const tree = treeFromText(P['arrange.tree']);
    if (tree) layoutTree = tree;
  }
  applyFacets();
  if (P['graph.camera'] && gViews[0]) {
    const [yw, pt, zm, px, py] = P['graph.camera'].split(' ').map(parseFloat);
    Object.assign(gViews[0], { yaw: yw, pitch: pt, zoom: zm });
    if (!Number.isNaN(px)) gViews[0].pan = { x: px, y: py || 0 };
  }
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
  // legacy keys, honored while the tree keeps its default shape
  const lim = { reader: [0.06, 0.86], right: [0.06, 0.86], top: [0.12, 0.92] };
  const v = Math.max(lim[which][0], Math.min(lim[which][1], frac));
  const t = layoutTree;
  if (which === 'reader' && Array.isArray(t) && t[2] === 'grammar') t[1] = v;
  else if (which === 'right' && Array.isArray(t) && Array.isArray(t[3]) && t[3][2] === 'document') {
    t[3][1] = Math.max(0.05, Math.min(0.95, 1 - v / (1 - t[1])));
  } else if (which === 'top' && Array.isArray(t) && Array.isArray(t[3]) && Array.isArray(t[3][3]) && t[3][3][0] === 'v') {
    t[3][3][1] = v;
  } else return;
  layoutFacets();
  if (post) postPolicyDebounced('arrange.' + which, v.toFixed(3));
  ask();
}
