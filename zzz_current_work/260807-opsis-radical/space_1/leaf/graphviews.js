/* opsis leaf — the graph views inside a room.

   A room's graph is the SAME picture as the facet's, asked for at the size
   of the room it is in. This file used to hold a second copy of every
   layout and every draw — flat, arcs and a whole 3-D projection — which is
   how the two could disagree about what a grammar looks like. */

'use strict';

function bootGraphViews(scope) {
  for (const view of scope.querySelectorAll('.gview')) {
    if (view.dataset.armed) continue;
    view.dataset.armed = '1';
    view._mode = 'flat';
    view._pan = { x: 0, y: 0 };
    armGraphView(view);
    pvDrawView(view);
  }
}

function armGraphView(view) {
  const canvas = view.querySelector('canvas');
  view.addEventListener('click', (ev) => {
    const tab = ev.target.closest('.gtab');
    if (tab) {
      view._mode = tab.dataset.view;
      for (const b of view.querySelectorAll('.gtab')) b.classList.toggle('on', b === tab);
      pvDrawView(view);
      return;
    }
    // a painted door is followed here too — one hit test, any picture
    const box = canvas.getBoundingClientRect();
    const door = view._painted && doorAt(view._painted, ev.clientX - box.left,
      ev.clientY - box.top, view._pan, view._scale || 1);
    if (door) { cur.rule = door.goes; ask(); }
  });
  let drag = null;
  canvas.addEventListener('pointerdown', (ev) => {
    drag = { x: ev.clientX - view._pan.x, y: ev.clientY - view._pan.y };
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    view._pan = { x: ev.clientX - drag.x, y: ev.clientY - drag.y };
    pvDrawView(view);
  });
  canvas.addEventListener('pointerup', () => { drag = null; });
}

async function pvDrawView(view) {
  const canvas = view.querySelector('canvas');
  const host = canvas.parentElement;
  const wide = Math.max(320, host ? host.clientWidth : 700);
  const view3 = view._mode === '3d' ? 'rings' : view._mode;
  const said = await loadDrawing(`graph:${view.dataset.place}:${view3}`,
    `&view=${view3}&box=${Math.round(wide)}x420&t=${Math.round(cur.t)}`,
    'graph');
  if (!said) return;
  const scale = Math.min(1, wide / Math.max(1, said.w));
  view._painted = said;
  view._scale = scale;
  canvas.style.height = Math.min(520, Math.max(220, said.h * scale + 20)) + 'px';
  paint(canvas, said, view._pan, scale);
}

async function pollRoutes() {
  const text = await (await fetch('/routes')).text();
  const r = {};
  for (const line of text.split('\n')) {
    const k = line.slice(0, line.indexOf(' '));
    r[k] = line.slice(k.length + 1);
  }
  const el = $('routes');
  if (r.status === 'pending') {
    el.textContent = ` · route: ${r.primary} ${r.primary_seconds}s · the other engine is running…`;
    setTimeout(pollRoutes, 1200);
  } else if (r.status === 'done') {
    el.textContent = ` · route: ${r.primary} ${r.primary_seconds}s · ${r.name} ${r.seconds}s · `
      + (r.parity === 'holds' ? 'both engines built the same value — holds'
         : r.parity === 'unmeasured' ? 'parity unmeasured' : 'PARITY FAILS');
    el.className = r.parity === 'holds' ? 'holds' : '';
  } else {
    const pos = parseInt(r.pos ?? '-1', 10);
    el.textContent = ` · route: ${r.primary} ${r.primary_seconds}s · ${r.name} ended`
      + (pos >= 0 ? ` at char ${pos.toLocaleString()} — where the fast road stops` : `: ${r.words}`);
  }
}

(async () => {
  wireGraph();  // the facet view must exist before boot applies reader.mode/camera policy
  await boot(false);
  wire();
  wirePins();
  wireChip();
  wireTransport();
  wireSpineZoom();
  wireTextZoom();
  wireChartZoom();
  wireClockSelect();
  wireFacetDrops();
  wireRailChip();
  wireTune();
  wireSeams();
  pollRoutes();
  pollPolicy();
  const q = new URLSearchParams(location.search);
  if (q.has('t')) { cur.t = Math.min(+q.get('t'), S.doc.length); cur.follow = true; ask(); }
  if (q.has('sel')) {
    cur.sel = deepestAt(+q.get('sel'));
    render();
    if (cur.sel >= 0) chipAt(S.spans[cur.sel].s, true);
  }
  if (q.has('rule')) { cur.rule = q.get('rule'); ask(); }
  if (q.has('break')) { const off = +q.get('break'); applyEdit(off, off + 1, '\u00a7'); }
  if (q.has('pin')) {
    for (const off of q.get('pin').split(',')) addPin(deepestAt(+off));
  }
  if (q.has('graph')) setGraph(true);
  if (q.has('gpin')) { setGraph(true); graphPin(); }
  if (q.has('rail')) { for (const name of q.get('rail').split(',')) railPin(name); }
  if (q.has('focus')) { focusOn = true; $('gfocus').classList.add('on'); drawGraph(); }
  if ([...q.keys()].length === 0) setTimeout(play, 600);  // deterministic states do not animate
})();

const _q = new URLSearchParams(location.search);
// the instrument can be SENT to a state, not only navigated into one
if (_q.has('pop')) setTimeout(() => popFacet(_q.get('pop')), 800);
if (_q.has('clone')) setTimeout(() => cloneFacet(_q.get('clone')), 900);
if (_q.has('strata')) setTimeout(openStrata, 700);
if (_q.has('place')) setTimeout(() => openPlace(_q.get('place')), 900);
if (_q.has('rooms')) setTimeout(() => openPlace('index'), 900);
document.addEventListener('click', (e) => {
  if (e.target && e.target.id === 'placeBack') closePlace();
});
