/* opsis leaf — the railroad — one rule's body as track.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── the railroad — one rule's body as track: sequence rides the line,
   choice splits it, repetition loops it. Structure from the wire; geometry here. ── */

const railCache = new Map();

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
