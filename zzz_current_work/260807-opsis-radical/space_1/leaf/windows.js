/* opsis leaf — pinned windows, and time.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

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
  // a span that covers nothing is not a defect and not a gap: the rule
  // derived ε, so the model holds an object the text does not show. Saying
  // so is the difference between structure and noise.
  const extent = s.e > s.s
    ? `${s.s.toLocaleString()}..${s.e.toLocaleString()}`
    : `at ${s.s.toLocaleString()} — matched NO text (the rule derives ε)`;
  return `${S.ruleNames[s.r]}${f ? ' · field ' + f : ''} · ${extent} · d${s.d}`
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
