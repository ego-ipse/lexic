/* opsis leaf — the IR surface — a value drawn as what it IS.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── the IR surface: a value drawn as what it IS, never as a string ──
   Identity (one object reached N times is ONE node with N edges arriving),
   tier (a scalar IS its payload; a record's edges are its FIELD NAMES),
   absence (IrNone is a value), refusal (IrLambda carries a callable, so
   the notation refuses it — the boundary is part of the picture). */

function bootIrViews(scope) {
  for (const view of scope.querySelectorAll('.irv')) {
    if (view.dataset.armed) return;
    view.dataset.armed = '1';
    view._trail = [];
    loadIr(view);
  }
}

async function loadIr(view) {
  const url = `/irvalue?place=${encodeURIComponent(view.dataset.place)}`
    + `&path=${encodeURIComponent(view.dataset.path || '')}`;
  const text = await (await fetch(url)).text();
  drawIr(view, parseIr(text));
}

function parseIr(text) {
  const ir = { meta: {}, nodes: [], edges: [], kids: [] };
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('#NODES ') || line.startsWith('#IREDGES ')
        || line.startsWith('#KIDS ')) {
      const [tag, count] = line.split(' ');
      const n = parseInt(count, 10);
      const rows = lines.slice(i + 1, i + 1 + n);
      i += n;
      if (tag === '#NODES') {
        ir.nodes = rows.map((r) => {
          const p = r.split(' ');
          return { i: +p[0], type: p[1], tier: p[2], kids: +p[3], subtree: +p[4],
                   refs: +p[5], refused: p[6] === '1', payload: p.slice(7).join(' ') };
        });
      } else if (tag === '#IREDGES') {
        ir.edges = rows.map((r) => {
          const p = r.split(' ');
          return { a: +p[0], b: +p[1], label: p.slice(2).join(' ') };
        });
      } else {
        ir.kids = rows.map((r) => {
          const p = r.split(' ');
          return { i: +p[0], label: p[1], type: p[2], tier: p[3], kids: +p[4],
                   payload: p.slice(5).join(' ') };
        });
      }
    } else if (line.includes(' ')) {
      const k = line.slice(0, line.indexOf(' '));
      ir.meta[k] = line.slice(k.length + 1);
    }
  }
  return ir;
}

function irTree(ir) {
  const kids = new Map();
  for (const e of ir.edges) {
    if (!kids.has(e.a)) kids.set(e.a, []);
    kids.get(e.a).push(e);
  }
  const drawn = new Set();
  const out = [];
  const walk = (idx, depth, label) => {
    const n = ir.nodes[idx];
    if (!n || depth > 9 || out.length > 400) return;
    const again = drawn.has(idx);
    drawn.add(idx);
    out.push({ n, depth, label, again });
    if (again) return;                       // one object, drawn once
    for (const e of (kids.get(idx) || [])) walk(e.b, depth + 1, e.label);
  };
  walk(0, 0, '');
  return out;
}

function irRow(row) {
  const { n, depth, label, again } = row;
  const pad = 'style="padding-left:' + (depth * 15) + 'px"';
  const field = label ? `<span class="irfield">${stEsc(label)}</span>` : '';
  const share = n.refs > 1
    ? `<span class="irshare" title="one object, reached ${n.refs} times">`
      + `↩ ${n.refs}×</span>` : '';
  if (again) {
    return `<div class="irrow t-${n.tier} irdup" ${pad}>${field}`
      + `<span class="irtype">${stEsc(n.type)}</span>`
      + `<span class="irkids">the same object, drawn above</span>${share}</div>`;
  }
  // a record can be BOTH: it carries payload (its primitive fields — a
  // rule's name, a quantifier's bound) and it has children. Showing only the
  // subtree count made every rule row anonymous.
  const pay = n.payload ? `<span class="irpay">${stEsc(n.payload)}</span>` : '';
  const body = n.kids
    ? pay + `<span class="irkids">${n.subtree} in subtree</span>`
    : pay;
  return `<div class="irrow t-${n.tier}${n.refused ? ' refused' : ''}" ${pad}`
    + ` data-zoom="${n.i}">${field}<span class="irtype">${stEsc(n.type)}</span>`
    + `${body}${share}</div>`;
}

function drawIr(view, ir) {
  const m = ir.meta;
  const trail = view._trail.map((t, i) =>
    `<span class="ircrumb" data-up="${i}">${stEsc(t)}</span>`).join(' › ');
  const shared = +m.shared || 0;
  const facts = [
    `${m.nodes} unique nodes`, `${m.edges} edges`,
    shared ? `${shared} shared — reached ${m.sharedrefs} times` : 'nothing shared',
    +m.refused ? `${m.refused} REFUSED (IrLambda: a callable — the notation's
      boundary)` : null,
    `tiers ${m.tiers || ''}`,
  ].filter(Boolean);
  view.querySelector('.irhead').innerHTML =
    `<div class="irpath">${trail ? trail + ' › ' : ''}`
    + `<b>${stEsc(m.type || '')}</b> <span class="irtier">${stEsc(m.tier || '')}</span></div>`
    + `<div class="irfacts">${stEsc(facts.join(' · '))}</div>`;
  const rows = irTree(ir);
  const body = rows.length > 1
    ? `<div class="irtree">${rows.map(irRow).join('')}</div>`
    : `<div class="irleaf">${stEsc(m.type)} — a leaf: it IS its payload`
      + `<b>${stEsc(ir.nodes.length ? ir.nodes[0].payload : '')}</b></div>`;
  view.querySelector('.irbody').innerHTML = body;
  // zoom by CHILD INDEX of the root: the child rows carry their edge order
  const rootKids = ir.kids.map((k) => k.i);
  view.querySelectorAll('.irrow[data-zoom]').forEach((el, i) => {
    if (i === 0) return;
    el.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const depth = +(el.style.paddingLeft.replace('px', '') || 0) / 15;
      if (depth !== 1) return;               // one step at a time, honestly
      const order = [...view.querySelectorAll('.irrow')].filter(
        (r) => (+(r.style.paddingLeft.replace('px', '') || 0) / 15) === 1);
      const idx = order.indexOf(el);
      if (idx < 0 || idx >= rootKids.length) return;
      view._trail.push(m.type);
      view.dataset.path = (view.dataset.path ? view.dataset.path + '/' : '') + idx;
      loadIr(view);
    });
  });
  for (const el of view.querySelectorAll('.ircrumb')) {
    el.addEventListener('click', () => {
      const depth = +el.dataset.up;
      view._trail = view._trail.slice(0, depth);
      view.dataset.path = (view.dataset.path || '').split('/').slice(0, depth).join('/');
      loadIr(view);
    });
  }
}
