/* opsis leaf — gestures — what the hand does to the instrument.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

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
  window.addEventListener('resize', () => { layoutFacets(); ask(); });
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
