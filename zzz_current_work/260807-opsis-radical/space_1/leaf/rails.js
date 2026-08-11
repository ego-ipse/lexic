/* opsis leaf — the railroad — one rule's body as track.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── the railroad — one rule's body as track: sequence rides the line,
   choice splits it, repetition loops it. Structure from the wire; geometry here. ── */

const RAIL = { bh: 20, padx: 7, gap: 16, vgap: 9, loop: 13 };
const railCache = new Map();
let railInk = null;

function railColors() {
  if (!railInk) {
    const cs = getComputedStyle(document.documentElement);
    railInk = Object.fromEntries(['cool', 'warm', 'violet', 'dim', 'dimmer', 'ink', 'red', 'field']
      .map((k) => [k, cs.getPropertyValue('--' + k).trim()]));
  }
  return railInk;
}

function railFont() {
  return '11px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
}

async function fetchRail(rule) {
  if (railCache.has(rule)) return railCache.get(rule);
  const text = await fetch('/rail?rule=' + encodeURIComponent(rule)).then((r) => r.text());
  if (text.startsWith('no such rule')) { railCache.set(rule, null); return null; }
  const root = { k: 'seq', payload: '', kids: [] };
  const stack = [root];
  for (const ln of text.split('\n').slice(1)) {
    const m = ln.match(/^(\d+) (\S+)(?: (.*))?$/);
    if (!m) continue;
    const node = { k: m[2], payload: m[3] || '', kids: [] };
    stack[+m[1]].kids.push(node);
    stack[+m[1] + 1] = node;
  }
  const tree = root.kids.length === 1 ? root.kids[0] : root;
  railCache.set(rule, tree);
  return tree;
}

function railMeasure(n, cx) {
  for (const kid of n.kids) railMeasure(kid, cx);
  if (n.k === 'seq') {
    n.cy = Math.max(...n.kids.map((kid) => kid.cy));
    n.w = n.kids.reduce((a, kid) => a + kid.w, 0) + RAIL.gap * (n.kids.length - 1);
    n.h = n.cy + Math.max(...n.kids.map((kid) => kid.h - kid.cy));
  } else if (n.k === 'alt') {
    n.w = Math.max(...n.kids.map((kid) => kid.w)) + 56;
    n.h = n.kids.reduce((a, kid) => a + kid.h, 0) + RAIL.vgap * (n.kids.length - 1);
    n.cy = n.kids[0].cy;
  } else if (n.k === 'many') {
    const [lo, hi] = n.payload.split(' ').map(Number);
    const kid = n.kids[0];
    n.bypass = lo === 0;
    n.loop = hi !== 1;
    n.count = lo > 1 || hi > 1 ? `${lo}..${hi < 0 ? '∞' : hi}` : '';
    n.w = kid.w + 40;
    n.h = kid.h + (n.bypass ? RAIL.loop : 0) + (n.loop ? RAIL.loop : 0) + (n.count ? 10 : 0);
    n.cy = kid.cy + (n.bypass ? RAIL.loop : 0);
  } else if (n.k === 'not' || n.k === 'alpha') {
    const kid = n.kids[0];
    n.tag = n.k === 'not' ? '¬ none of' : '⟨' + n.payload + '⟩';
    n.w = Math.max(kid.w + 12, cx.measureText(n.tag).width + 12);
    n.h = kid.h + 20;
    n.cy = kid.cy + 16;
  } else {
    let label = n.k === 'nil' ? 'ε' : n.k === 'class' ? '[' + n.payload + ']' : n.payload || 'ε';
    if (label.length > 30) label = label.slice(0, 29) + '…';
    n.label = label;
    n.w = Math.max(26, Math.ceil(cx.measureText(label).width) + RAIL.padx * 2);
    n.h = RAIL.bh;
    n.cy = RAIL.bh / 2;
  }
}

function railLine(cx, x0, y0, x1, y1) {
  cx.strokeStyle = railColors().dim;
  cx.lineWidth = 1.2;
  cx.beginPath();
  cx.moveTo(x0, y0);
  cx.lineTo(x1, y1);
  cx.stroke();
}

function railBranch(cx, x0, y0, x1, y1) {
  cx.strokeStyle = railColors().dim;
  cx.lineWidth = 1.2;
  cx.beginPath();
  cx.moveTo(x0, y0);
  cx.bezierCurveTo((x0 + x1) / 2, y0, (x0 + x1) / 2, y1, x1, y1);
  cx.stroke();
}

function railArch(cx, x0, x1, y, dy) {
  cx.strokeStyle = railColors().dim;
  cx.lineWidth = 1.2;
  cx.beginPath();
  cx.moveTo(x0, y);
  cx.bezierCurveTo(x0 + 2, y + dy, x1 - 2, y + dy, x1, y);
  cx.stroke();
}

function railDraw(n, cx, x, y, hits) {
  const yE = y + n.cy;
  if (n.k === 'seq') {
    let ax = x;
    n.kids.forEach((kid, i) => {
      if (i) { railLine(cx, ax, yE, ax + RAIL.gap, yE); ax += RAIL.gap; }
      railDraw(kid, cx, ax, yE - kid.cy, hits);
      ax += kid.w;
    });
  } else if (n.k === 'alt') {
    const inx = x + 28, outx = x + n.w - 28;
    let ay = y;
    for (const kid of n.kids) {
      const ky = ay + kid.cy;
      railBranch(cx, x, yE, inx, ky);
      railDraw(kid, cx, inx, ay, hits);
      railLine(cx, inx + kid.w, ky, outx, ky);
      railBranch(cx, x + n.w, yE, outx, ky);
      ay += kid.h + RAIL.vgap;
    }
  } else if (n.k === 'many') {
    const kid = n.kids[0];
    const kx = x + 20;
    railLine(cx, x, yE, kx, yE);
    railDraw(kid, cx, kx, yE - kid.cy, hits);
    railLine(cx, kx + kid.w, yE, x + n.w, yE);
    if (n.bypass) railArch(cx, x + 5, x + n.w - 5, yE, -(kid.cy + 10));
    if (n.loop) railArch(cx, kx - 6, kx + kid.w + 6, yE, kid.h - kid.cy + 10);
    if (n.count) {
      cx.fillStyle = railColors().dim;
      cx.fillText(n.count, x + (n.w - cx.measureText(n.count).width) / 2, yE + kid.h - kid.cy + RAIL.loop + 8);
    }
  } else if (n.k === 'not' || n.k === 'alpha') {
    const kid = n.kids[0];
    const kx = x + 6;
    railLine(cx, x, yE, kx, yE);
    railDraw(kid, cx, kx, y + 16, hits);
    railLine(cx, kx + kid.w, yE, x + n.w, yE);
    cx.setLineDash([3, 3]);
    cx.strokeStyle = railColors().dim;
    cx.strokeRect(x + 1, y + 1, n.w - 2, n.h - 2);
    cx.setLineDash([]);
    cx.fillStyle = n.k === 'not' ? railColors().red : railColors().dim;
    cx.fillText(n.tag, x + 5, y + 11);
  } else {
    const C = railColors();
    let color = { ref: C.cool, lit: C.warm, class: C.violet }[n.k] || C.dim;
    let textColor = color;
    if (n.k === 'ref' && n.label === hotRule()) {
      // the same light the rule's chip carries when hovered
      cx.fillStyle = C.warm;
      cx.fillRect(x, y, n.w, n.h);
      color = C.warm;
      textColor = C.field;
    } else if (n.k === 'ref' && n.label === cur.rule) {
      color = C.violet;
      textColor = C.violet;
    }
    cx.strokeStyle = color;
    cx.lineWidth = 1;
    cx.beginPath();
    if (n.k === 'lit') cx.roundRect(x, y, n.w, n.h, 9);
    else cx.rect(x, y, n.w, n.h);
    cx.stroke();
    cx.fillStyle = textColor;
    cx.fillText(n.label, x + (n.w - cx.measureText(n.label).width) / 2, yE + 3.5);
    if (n.k === 'ref') hits.push({ x, y, w: n.w, h: n.h, rule: n.label });
  }
}

let railsAll = null;
let railsLoading = false;
let railsLayout = null;

function parseRailTree(lines) {
  const root = { k: 'seq', payload: '', kids: [] };
  const stack = [root];
  for (const ln of lines) {
    const m = ln.match(/^(\d+) (\S+)(?: (.*))?$/);
    if (!m) continue;
    const node = { k: m[2], payload: m[3] || '', kids: [] };
    stack[+m[1]].kids.push(node);
    stack[+m[1] + 1] = node;
  }
  return root.kids.length === 1 ? root.kids[0] : root;
}

async function fetchRails() {
  if (railsAll || railsLoading) return;
  railsLoading = true;
  const text = await fetch('/rails').then((r) => r.text());
  railsAll = new Map();
  let name = null, lines = [];
  for (const ln of text.split('\n')) {
    if (ln.startsWith('#RAIL ')) {
      if (name !== null) railsAll.set(name, parseRailTree(lines));
      name = ln.split(' ')[1];
      lines = [];
    } else {
      lines.push(ln);
    }
  }
  if (name !== null) railsAll.set(name, parseRailTree(lines));
  railsLayout = null;
  drawGraph();  // one redraw, when the rails arrive
}

function railsOrder() {
  const names = Object.keys(S.depths).length ? Object.keys(S.depths) : S.ruledefs.map((r) => r.name);
  const order = S.ruledefs.map((r) => r.name).filter((n) => names.includes(n));
  for (const n of names) if (!order.includes(n)) order.push(n);
  return order;
}

function buildRailsLayout(cx) {
  cx.font = railFont();
  const gap = 10 + gTune.levelstep / 8;
  const entries = [];
  let y = 0, maxw = 0;
  for (const name of railsOrder()) {
    const tree = railsAll.get(name);
    if (!tree) continue;
    railMeasure(tree, cx);
    entries.push({ rule: name, tree, x: 26, y: y + 14 });
    maxw = Math.max(maxw, tree.w + 66);
    y += 14 + tree.h + gap;
  }
  railsLayout = { entries, byName: new Map(entries.map((e) => [e.rule, e])), w: maxw, h: y };
}

function drawRailsView(v) {
  const wrap = v.wrap, cv = v.cv;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w || !h) return;
  v.chips.style.display = '';
  if (!railsAll) { fetchRails(); return; }  // a guarded call schedules nothing
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const cx = cv.getContext('2d');
  if (!railsLayout) buildRailsLayout(cx);
  const L = railsLayout;
  const k = Math.max(Math.min((w - 24) / Math.max(60, L.w), 1.35), 0.8) * v.zoom;
  const mx = L.w / 2, my = L.h / 2;
  if (!v.touched) {
    v.pan.x = 16 - w / 2 + mx * k;  // untouched camera frames the top-left —
    v.pan.y = 12 - h / 2 + my * k;  // the start rule; pan explores downward
  }
  const tx = w / 2 - mx * k + v.pan.x, ty = h / 2 - my * k + v.pan.y;
  v.rk = k; v.rtx = tx; v.rty = ty;
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  cx.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);
  cx.font = railFont();
  const hits = [];
  const uy0 = -ty / k - 40, uy1 = (h - ty) / k + 40;
  for (const e of L.entries) {
    if (e.y + e.tree.h < uy0 || e.y > uy1) continue;
    const yE = e.y + e.tree.cy;
    railLine(cx, e.x - 14, yE, e.x, yE);
    railLine(cx, e.x + e.tree.w, yE, e.x + e.tree.w + 14, yE);
    cx.fillStyle = railColors().dim;
    for (const ex of [e.x - 14, e.x + e.tree.w + 14]) {
      cx.beginPath();
      cx.arc(ex, yE, 2.5, 0, Math.PI * 2);
      cx.fill();
    }
    railDraw(e.tree, cx, e.x, e.y, hits);
  }
  v.railHits = hits;
  const start = Object.keys(S.depths).find((n) => S.depths[n] === 0) || '';
  const hot = hotRule();
  for (const el of v.chips.children) {
    const e = L.byName.get(el.dataset.name);
    if (!e) { el.style.display = 'none'; continue; }
    el.style.display = '';
    el.style.left = (e.x - 12) * k + tx + 'px';
    el.style.top = (e.y - 6) * k + ty + 'px';
    el.style.transform = 'translate(0, -100%)';
    el.style.zIndex = 5;
    el.classList.add('near');
    el.classList.remove('dot');
    el.classList.toggle('start', el.dataset.name === start);
    el.classList.toggle('marked', el.dataset.name === cur.rule);
    el.classList.toggle('hot', el.dataset.name === hot);
    el.classList.remove('faded');
  }
}

let railChipRule = '';

function railChipShow(rule, x, y) {
  railChipRule = rule;
  const chip = $('railchip');
  chip.style.left = Math.max(8, Math.min(x + 6, window.innerWidth - 86)) + 'px';
  chip.style.top = Math.max(8, Math.min(y - 34, window.innerHeight - 42)) + 'px';
  chip.hidden = false;
}

function wireRailChip() {
  const chip = $('railchip');
  chip.addEventListener('pointerdown', (e) => e.preventDefault());
  chip.addEventListener('click', () => {
    if (railChipRule) railPin(railChipRule);
    chip.hidden = true;
  });
  window.addEventListener('pointerdown', (e) => {
    if (!e.target.closest('#railchip')) chip.hidden = true;
  }, true);
  $('grammarScroll').addEventListener('scroll', () => { chip.hidden = true; });
}

function railsGoto(v, rule) {
  const e = railsLayout && railsLayout.byName.get(rule);
  if (!e || v.rk === undefined) return;
  v.touched = true;
  v.pan.y += 34 - (e.y * v.rk + v.rty);
  persistView(v);
  drawGraphView(v);
}
