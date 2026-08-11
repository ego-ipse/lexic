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

async function fetchRail(rule) {
  // one rule's track, with its MEASUREMENT — the boxes arrive in a #BOX
  // block beside the lines, and a tree parsed without them has no sizes at
  // all, which is a pinned window drawing nothing you can see.
  if (railCache.has(rule)) return railCache.get(rule);
  const text = await fetch('/rail?rule=' + encodeURIComponent(rule))
    .then((r) => r.text());
  if (text.startsWith('no such rule')) { railCache.set(rule, null); return null; }
  const rows = text.split('\n');
  const lines = [], boxes = [];
  let where = 'lines';
  for (const ln of rows.slice(1)) {
    if (ln.startsWith('#BOX ')) { where = 'boxes'; continue; }
    if (ln) (where === 'lines' ? lines : boxes).push(ln);
  }
  const tree = parseRailTree(lines, parseRailBoxes(boxes));
  railCache.set(rule, tree);
  return tree;
}

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

function railCell(cx) {
  // the cell this railroad is being drawn into: one character wide, one row
  // tall. Everything else about its size was decided by the reading.
  cx.font = railFont();
  return { w: Math.max(5, cx.measureText('0').width), h: RAIL.bh };
}

function railMeasure(n, cx, cell) {
  const box = cell || railCell(cx);
  n.w = (n.cw || 6) * box.w;
  n.h = (n.ch || 1) * box.h;
  n.cy = (n.ccy || 0.5) * box.h;
  if (n.k === 'many') {
    const [lo, hi] = n.payload.split(' ').map(Number);
    n.bypass = lo === 0;
    n.loop = hi !== 1;
    n.count = lo > 1 || hi > 1 ? `${lo}..${hi < 0 ? '∞' : hi}` : '';
  } else if (n.k === 'not' || n.k === 'alpha') {
    n.tag = n.k === 'not' ? '¬ none of' : '⟨' + n.payload + '⟩';
  }
  for (const kid of n.kids) railMeasure(kid, cx, box);
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

function parseRailTree(lines, boxes) {
  // the nodes and their ROOM arrive together, box i for line i, measured in
  // columns and rows. The leaf multiplies by the cell it draws into — the
  // one measurement it genuinely owns.
  const root = { k: 'seq', payload: '', kids: [] };
  const stack = [root];
  let at = 0;
  for (const ln of lines) {
    const m = ln.match(/^(\d+) (\S+)(?: (.*))?$/);
    if (!m) continue;
    const box = boxes[at++] || { w: 6, h: 1, cy: 0.5, label: '' };
    const node = {
      k: m[2], payload: m[3] || '', kids: [],
      cw: box.w, ch: box.h, ccy: box.cy, label: box.label,
    };
    stack[+m[1]].kids.push(node);
    stack[+m[1] + 1] = node;
  }
  return root.kids.length === 1 ? root.kids[0] : root;
}

function parseRailBoxes(lines) {
  return lines.map((ln) => {
    const p = ln.split(' ');
    return { w: +p[0], h: +p[1], cy: +p[2], label: p.slice(3).join(' ') };
  });
}

async function fetchRails() {
  if (railsAll || railsLoading) return;
  railsLoading = true;
  const text = await fetch('/rails').then((r) => r.text());
  railsAll = new Map();
  let name = null, lines = [], boxes = [], where = 'lines';
  const keep = () => {
    if (name !== null) railsAll.set(name, parseRailTree(lines, parseRailBoxes(boxes)));
  };
  for (const ln of text.split('\n')) {
    if (ln.startsWith('#RAIL ')) {
      keep();
      name = ln.split(' ')[1];
      lines = []; boxes = []; where = 'lines';
    } else if (ln.startsWith('#BOX ')) {
      where = 'boxes';
    } else if (ln) {
      (where === 'lines' ? lines : boxes).push(ln);
    }
  }
  keep();
  railsLayout = null;
  drawGraph();  // one redraw, when the rails arrive
}

function railsOrder() {
  const names = Object.keys(S.depths).length ? Object.keys(S.depths) : S.ruledefs.map((r) => r.name);
  const order = S.ruledefs.map((r) => r.name).filter((n) => names.includes(n));
  for (const n of names) if (!order.includes(n)) order.push(n);
  return order;
}

// which rule the chip is offering to pin. Its declaration went out with a
// deletion; in strict mode assigning to an undeclared name THROWS, so the
// chip stopped appearing at all rather than appearing wrong.
let railChipRule = '';

function railPin(rule) {
  // a railroad in its own window: the pin machinery draws it, loads it and
  // remembers it like any other pin. This went out with a deletion, so the
  // chip had nothing to call and the pop-up never appeared.
  const at = pins.length;
  const p = {
    id: ++pinSeq, kind: 'rail', rule, gen: S.meta.generation,
    x: 260 + (at % 6) * 30, y: 120 + (at % 6) * 30, w: 0, h: 0, hist: [],
  };
  pins.push(p);
  renderPins();
  postPolicy(`pin.${p.id}`, pinPolicyValue(p));
  return p;
}

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
  // the drawing says where every rule's name was painted; going to one is
  // panning until that place is at the top of the view
  const said = v.painted && v.painted.said;
  if (!said) return;
  const at = (said.hits || []).find((h) => h.goes === rule);
  if (!at) return;
  v.touched = true;
  v.pan = { x: v.pan.x, y: 24 - at.y * (v.painted.scale || 1) };
  drawGraphView(v);
}
