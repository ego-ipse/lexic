/* opsis leaf — boot.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── boot ── */

async function boot(keep) {
  const text = await (await fetch('/scene')).text();
  const t0 = keep ? Math.min(cur.t, 1e12) : 0;
  S = parseScene(text);
  cur.sel = -1; cur.hover = -1; cur.docSel = null;
  $('docText').textContent = S.doc;
  buildGutter(S.lineStarts.length);
  buildCode($('grammarBody'), S.readerLines, false);
  fetchVerdicts();
  decorateVerdicts();
  measure();
  view0 = 0;
  sizeDocCanvases();
  gNodes = null;
  // the graph is a facet now — if it is open, it has something to draw
  graphOn = facetOn['graph'] !== false;
  if (graphOn) buildGraph();
  applyPolicy();
  renderLadder();
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
  else if (k === 'chart.clock') setClock(v);
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
  } else if (k === 'arrange.tree') {
    const tree = treeFromText(v);
    if (tree) { layoutTree = tree; applyFacets(); }
  } else if (k.startsWith('facet.')) {
    const name = k.slice(6);
    if (FACETS.includes(name)) { facetOn[name] = v !== 'off'; applyFacets(); }
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

function resetSubjectCaches() {
  railCache.clear();
  railsAll = null;
  railsLoading = false;
  railsLayout = null;
  verdictMap = null;
  verdictLoading = false;
  autoData = null;
  autoLoading = false;
  clockData = null;
  clockWaiting = false;
  colCache = new Map();
  colWaiting = false;
  clockHover = -1;
  clockHoverExt = null;
}

async function travel(i) {
  await fetch('/focus', { method: 'POST', body: 'focus ' + i }).catch(() => {});
  resetSubjectCaches();
  await boot(false);
}

function renderLadder() {
  // The strip is dead: the masthead carries ONE chip — where you are.
  // Clicking it pulls back to the strata: every reading at its level,
  // drawn as its own miniature; travel is choosing a card.
  const strip = $('ladder');
  if (!strip) return;
  strip.textContent = '';
  const focused = S.ladder.find((r) => r.focused);
  const chip = document.createElement('span');
  chip.className = 'rung on';
  chip.textContent = (focused ? focused.label : '…') + '  ∴';
  chip.title = 'pull back to the strata — every reading at its level';
  chip.addEventListener('click', openStrata);
  strip.appendChild(chip);
}
