/* opsis — the leaf. It paints what it is sent, welds the text planes to the
   same geometry, and reports what the hand did.

   It holds no tones, no fonts, no layout, no camera, no hit geometry and no
   idea what a grammar is. There is one geometry and it is not here, which is
   why nothing here can disagree with the picture. */

'use strict';

const paper = document.getElementById('paper');
const over = document.getElementById('over');
const planes = document.getElementById('planes');
const held = new Map();
const chosen = new Map();
const opened = {};
const asked = new URLSearchParams(location.search);
const only = asked.get('only') || '';
/* a window looks through its own layer over the session's policy: its view,
   its camera, its scroll are its own, and the cursor stays everyone's */
const win = asked.get('win') || '';

let frame = null;
let asking = false;
let queued = null;
let dragging = null;

const fill = (name) => frame.fills[name] || frame.fills.dim;
const edge = (name) => frame.edges[name];
const face = (name) => frame.fonts[name] || frame.font;

/* A gesture arriving mid-flight is NOT dropped: nudges of the same kind add
   up and the last of anything else wins, so a fast hand is answered. */
async function ask(gesture, body) {
  if (asking) { queued = merge(queued, gesture, body); return; }
  asking = true;
  try {
    const box = paper.getBoundingClientRect();
    const said = await fetch('/frame', {
      method: 'POST',
      body: `size ${Math.round(box.width)} ${Math.round(box.height)}\n`
        + (only ? `only ${only}\n` : '')
        + (win ? `win ${win}\n` : '')
        + (gesture || '')
        + (body === undefined ? '' : `\n${body}`),
    }).then((r) => r.text());
    const got = read(said);
    if (got) { frame = got; paint(); weld(); dropdowns(); }
  } finally {
    asking = false;
    if (queued) { const next = queued; queued = null; ask(next.gesture, next.body); }
  }
}

function merge(waiting, gesture, body) {
  if (!waiting) return { gesture, body };
  const a = waiting.gesture.split(' '), b = (gesture || '').split(' ');
  const adds = a[0] === b[0] && (a[0] === 'scroll' || a[0] === 'spin' || a[0] === 'step');
  if (adds && a[1] === b[1] && a[0] !== 'step') {
    return { gesture: [...a.slice(0, 2),
      ...a.slice(2).map((n, i) => +n + +b[i + 2])].join(' '), body };
  }
  if (a[0] === 'step' && b[0] === 'step') return { gesture: `step ${+a[1] + +b[1]}`, body };
  return { gesture, body };
}

function read(said) {
  const lines = said.split('\n');
  const font = (lines[0] || '').startsWith('#FONT ') ? lines[0].slice(6) : '';
  const tones = +(lines[1] || '').split(' ')[1] || 0;
  const fills = {}, edges = {}, fonts = {}, tracks = {};
  const into = { fill: fills, edge: edges, font: fonts, track: tracks };
  for (const row of lines.slice(2, 2 + tones)) {
    const p = row.split(' ');
    if (into[p[0]]) into[p[0]][p[1]] = p.slice(2).join(' ');
  }
  let i = 2 + tones;
  const head = (lines[i] || '').split(' ');
  if (head[0] !== '#FRAME') return null;
  const count = +head[4] || 0;
  const running = head[5] === '1';
  const marks = lines.slice(i + 1, i + 1 + count);
  i += 1 + count;
  const hits = [];
  if ((lines[i] || '').startsWith('#HITS ')) {
    const n = +lines[i].split(' ')[1] || 0;
    for (const row of lines.slice(i + 1, i + 1 + n)) {
      const p = row.split(' ');
      hits.push({ x: +p[0], y: +p[1], w: +p[2], h: +p[3], kind: p[4], goes: p[5],
                  run: +p[6] || 0, cell: +p[7] || 0 });
    }
    i += 1 + n;
  }
  const above = [];
  if ((lines[i] || '').startsWith('#OVER ')) {
    const n = +lines[i].split(' ')[1] || 0;
    above.push(...lines.slice(i + 1, i + 1 + n));
    i += 1 + n;
  }
  const picks = [];
  if ((lines[i] || '').startsWith('#PICKS ')) {
    const n = +lines[i].split(' ')[1] || 0;
    for (const row of lines.slice(i + 1, i + 1 + n)) {
      const p = row.split(' ');
      picks.push({ key: p[0], x: +p[1], y: +p[2], w: +p[3], h: +p[4], on: p[5],
                   options: p.slice(6).join(' ').split('|').map((o) => {
                     const at = o.indexOf(':');
                     return { value: o.slice(0, at), label: o.slice(at + 1) };
                   }) });
    }
    i += 1 + n;
  }
  const shown = [];
  if ((lines[i] || '').startsWith('#PLANES ')) {
    const n = +lines[i].split(' ')[1] || 0;
    for (const row of lines.slice(i + 1, i + 1 + n)) {
      const p = row.split(' ');
      shown.push({ name: p[0], x: +p[1], y: +p[2], w: +p[3], h: +p[4], row: +p[5],
                   cell: +p[6], top: +p[7], editable: p[8] === '1', chars: +p[9] });
    }
  }
  /* the texts ride raw at the end, counted in characters */
  let where = said.indexOf('\n#TEXT\n');
  where = where < 0 ? said.length : where + 7;
  for (const plane of shown) {
    plane.text = said.slice(where, where + plane.chars);
    where += plane.chars;
  }
  return { font, fills, edges, fonts, tracks, marks, hits, running,
           planes: shown, over: above, picks };
}

function paint() {
  strokes(paper, frame.marks);
  strokes(over, frame.over);
}

function strokes(canvas, marks) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr; canvas.height = h * dpr;
  }
  const cx = canvas.getContext('2d');
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  cx.font = frame.font;
  for (const mark of marks) {
    const p = mark.split(' ');
    if (p[0] === 'box') {
      cx.fillStyle = fill(p[5]);
      cx.fillRect(+p[1], +p[2], +p[3], +p[4]);
      const around = edge(p[5]);
      if (around) {
        cx.strokeStyle = around;
        cx.strokeRect(+p[1] + 0.5, +p[2] + 0.5, Math.max(+p[3] - 1, 1), +p[4]);
      }
    } else if (p[0] === 'ring') {
      cx.strokeStyle = fill(p[5]);
      cx.strokeRect(+p[1] + 0.5, +p[2] + 0.5, Math.max(+p[3] - 1, 1.5), +p[4]);
    } else if (p[0] === 'line') {
      cx.strokeStyle = fill(p[5]);
      cx.beginPath(); cx.moveTo(+p[1], +p[2]); cx.lineTo(+p[3], +p[4]); cx.stroke();
    } else if (p[0] === 'curve' || p[0] === 'bez') {
      const n = p[0] === 'curve' ? 6 : 8;
      cx.strokeStyle = fill(p[n + 1]);
      cx.beginPath();
      cx.moveTo(+p[1], +p[2]);
      if (n === 6) cx.quadraticCurveTo(+p[3], +p[4], +p[5], +p[6]);
      else cx.bezierCurveTo(+p[3], +p[4], +p[5], +p[6], +p[7], +p[8]);
      cx.stroke();
    } else if (p[0] === 'arc') {
      cx.strokeStyle = fill(p[4]);
      cx.beginPath(); cx.arc(+p[1], +p[2], +p[3], 0, Math.PI * 2); cx.stroke();
    } else if (p[0] === 'clip') {
      /* a facet is a window ONTO a picture: what runs past its edge stops
         there. One canvas has no layout to say that with, so it is a mark. */
      cx.save();
      cx.beginPath();
      cx.rect(+p[1], +p[2], +p[3], +p[4]);
      cx.clip();
    } else if (p[0] === 'unclip') {
      cx.restore();
      cx.font = frame.font;
    } else if (p[0] === 'text') {
      cx.font = face(p[4]);
      /* letter-spacing is part of a face: #title is tracked 0.18em, and a
         canvas that ignores it draws a visibly different word */
      cx.letterSpacing = frame.tracks[p[4]] || '0px';
      cx.fillStyle = fill(p[3]);
      cx.textAlign = p[5] === 'r' ? 'right' : 'left';
      cx.fillText(p.slice(6).join(' '), +p[1], +p[2]);
      cx.textAlign = 'left';
      cx.letterSpacing = '0px';
    }
  }
}

/* One real control per pick, on the geometry the frame sent. */
function dropdowns() {
  const want = new Set(frame.picks.map((p) => p.key));
  for (const [key, el] of chosen) {
    if (!want.has(key)) { el.remove(); chosen.delete(key); }
  }
  for (const pick of frame.picks) {
    let el = chosen.get(pick.key);
    if (!el) {
      el = document.createElement('select');
      el.className = 'pick';
      el.dataset.key = pick.key;
      el.addEventListener('change', () => ask(`set ${el.dataset.key} ${el.value}`));
      planes.appendChild(el);
      chosen.set(pick.key, el);
    }
    const said = pick.options.map((o) => o.value).join(' ');
    if (el.dataset.options !== said) {
      el.dataset.options = said;
      el.innerHTML = pick.options
        .map((o) => `<option value="${o.value}">${o.label}</option>`).join('');
    }
    el.value = pick.on;
    el.style.left = `${pick.x}px`;
    el.style.top = `${pick.y}px`;
    el.style.width = `${pick.w}px`;
    el.style.height = `${pick.h}px`;
  }
}

/* One real text element per plane, on the geometry the frame sent. */
function weld() {
  const want = new Set(frame.planes.map((p) => p.name));
  for (const [name, el] of held) {
    if (!want.has(name)) { el.remove(); held.delete(name); }
  }
  for (const plane of frame.planes) {
    let el = held.get(plane.name);
    if (!el) {
      el = document.createElement('textarea');
      el.className = 'plane';
      el.spellcheck = false;
      el.dataset.name = plane.name;
      el.addEventListener('input', () => ask(`text ${el.dataset.name}`, el.value));
      el.addEventListener('scroll', () => scrolled(el, plane));
      el.addEventListener('select', () => chose(el));
      el.addEventListener('mouseup', () => chose(el));
      el.addEventListener('keyup', () => chose(el));
      planes.appendChild(el);
      held.set(plane.name, el);
    }
    el.style.left = `${plane.x}px`;
    el.style.top = `${plane.y}px`;
    el.style.width = `${plane.w}px`;
    el.style.height = `${plane.h}px`;
    el.readOnly = !plane.editable;
    if (el.value !== plane.text && document.activeElement !== el) el.value = plane.text;
    const top = plane.top * plane.row;
    if (Math.abs(el.scrollTop - top) > plane.row) el.scrollTop = top;
  }
}

function scrolled(el, plane) {
  const line = Math.round(el.scrollTop / plane.row);
  if (line !== plane.top) { plane.top = line; ask(`scrolled ${plane.name} ${line}`); }
}

function chose(el) {
  const a = el.selectionStart, b = el.selectionEnd;
  if (a === chose.was && b === chose.until) return;
  chose.was = a; chose.until = b;
  ask(`sel ${el.dataset.name} ${a} ${b}`);
}

function under(ev, wanted) {
  const box = paper.getBoundingClientRect();
  const x = ev.clientX - box.left, y = ev.clientY - box.top;
  const hits = frame ? frame.hits : [];
  for (let i = hits.length - 1; i >= 0; i -= 1) {
    const h = hits[i];
    if ((h.kind === 'scroll') !== wanted) continue;
    if (x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) return h;
  }
  return null;
}

paper.addEventListener('click', (ev) => {
  const target = under(ev, false);
  if (!target) return;
  const box = paper.getBoundingClientRect();
  const into = target.cell > 0
    ? ` ${Math.max(0, Math.round((ev.clientX - box.left - target.run) / target.cell))}`
    : '';
  if (target.kind === 'seam') return;
  if (target.kind === 'pop' || target.kind === 'clone') {
    /* Two different things, and NEITHER is a browser window. POPPING takes
       the facet OUT of the grid — it is a window in the page now, floating
       over the arrangement, and the dock is where it comes back from.
       CLONING opens a SECOND one and leaves the grid alone. A real browser
       window is a different DOCUMENT: it cannot overlap the thing it was
       torn from, which is the entire reason to tear one off. */
    ask(`${target.kind} ${target.goes}`);
    return;
  }
  if (target.kind.includes('.')) {
    ask(`set ${target.kind} ${target.goes}`);
    return;
  }
  /* a rule chosen anywhere raises ▤ rail AT THE POINTER, so the click has
     to carry where it was — the frame has no other way to know */
  const where = target.kind === 'rule'
    ? ` ${Math.round(ev.clientX - box.left)} ${Math.round(ev.clientY - box.top)}`
    : '';
  ask(`at ${target.kind} ${target.goes}${into}${where}`);
});

/* dragging: a seam resizes, anything else in a picture turns it */
paper.addEventListener('pointerdown', (ev) => {
  /* what a drag STARTED on, falling back to the region it is in: a drag
     across a picture is about that picture even where nothing was hit */
  dragging = { x: ev.clientX, y: ev.clientY, on: under(ev, false) || under(ev, true) };
});
window.addEventListener('pointerup', (ev) => {
  /* a head dragged onto another surface is a TOPOLOGY change: where it was
     let go decides what happens, and deciding is the session's */
  if (dragging && dragging.on && dragging.on.kind === 'head' && dragging.moved) {
    const over = under(ev, true);
    if (over && over.goes !== dragging.on.goes) {
      const box = paper.getBoundingClientRect();
      ask(`move ${dragging.on.goes} ${over.goes}`
        + ` ${((ev.clientX - box.left - over.x) / over.w).toFixed(3)}`
        + ` ${((ev.clientY - box.top - over.y) / over.h).toFixed(3)}`);
    } else {
      ask('zone');
    }
  }
  dragging = null;
});
window.addEventListener('pointermove', (ev) => {
  if (!dragging) return;
  const dx = ev.clientX - dragging.x, dy = ev.clientY - dragging.y;
  if (Math.abs(dx) + Math.abs(dy) < 3) return;
  dragging.x = ev.clientX; dragging.y = ev.clientY;
  dragging.moved = true;
  const on = dragging.on;
  if (on && on.kind === 'head') {
    const over = under(ev, true);
    const box = paper.getBoundingClientRect();
    ask(over ? `zone ${on.goes} ${over.goes}`
      + ` ${((ev.clientX - box.left - over.x) / over.w).toFixed(3)}`
      + ` ${((ev.clientY - box.top - over.y) / over.h).toFixed(3)}` : 'zone');
    return;
  }
  if (on && on.kind.startsWith('dial.')) {
    const box = paper.getBoundingClientRect();
    const part = (ev.clientX - box.left - on.x) / on.w;
    ask(`dial ${on.kind.slice(5)} ${on.goes} ${Math.max(0, Math.min(1, part)).toFixed(3)}`);
    return;
  }
  if (on && on.kind === 'seam') {
    /* a split divides ITS OWN subtree: the share is measured inside the box
       the seam sits in, which the hit carries, not across the window */
    const box = paper.getBoundingClientRect();
    const along = on.w < on.h ? ev.clientX - box.left : ev.clientY - box.top;
    const part = (along - on.run) / (on.cell || 1);
    ask(`seam ${on.goes} ${part.toFixed(3)}`);
    return;
  }
  /* A drag says WHAT IT STARTED ON. Where it goes — a window moved, a
     graph turned, a corner resized — is the session's to decide, and it
     cannot decide it from two numbers alone. */
  ask(`spin ${on ? `${on.kind} ${on.goes}` : '- -'} ${dx} ${dy}`);
});

/* a stack of diagrams reads like a document: wheel scrolls, Ctrl+wheel zooms */
paper.addEventListener('wheel', (ev) => {
  const target = under(ev, true);
  if (!target) return;
  ev.preventDefault();
  const box = paper.getBoundingClientRect();
  const by = ev.deltaY > 0 ? 1 : -1;
  /* WHERE in the thing, as a fraction of it. A zoom that does not keep the
     point under the pointer under the pointer is a zoom you have to chase. */
  const fx = ((ev.clientX - box.left - target.x) / target.w).toFixed(3);
  const fy = ((ev.clientY - box.top - target.y) / target.h).toFixed(3);
  ask(`${ev.ctrlKey ? 'zoom' : 'scroll'} ${target.goes} ${by} ${fx} ${fy}`);
}, { passive: false });

/* Keys are REPORTED, not interpreted: whether Space is a letter or the
   transport depends on what has the hand, and that is not known here. */
const NAMED = new Set(['Space', 'Escape', 'Home', 'End', 'ArrowLeft', 'ArrowRight',
                       'Ctrl+Enter', 'Ctrl+s', 'Ctrl+p', 'p', 'g', '[', ']']);
window.addEventListener('keydown', (ev) => {
  const typing = document.activeElement && document.activeElement.classList.contains('plane');
  const name = (ev.ctrlKey ? 'Ctrl+' : '') + (ev.key === ' ' ? 'Space' : ev.key);
  if (typing && !ev.ctrlKey && name !== 'Escape') return;
  if (!NAMED.has(name)) return;
  ev.preventDefault();
  ask(`key ${name}`);
});

/* hover: reported only when what is under the pointer CHANGES, so a hand
   moving across a facet is one gesture, not a thousand */
let over_what = '';
paper.addEventListener('pointermove', (ev) => {
  if (dragging) return;
  const target = under(ev, false);
  const now = target ? `${target.kind} ${target.goes}` : '';
  if (now === over_what) return;
  over_what = now;
  ask(`hover ${now}`);
});

window.addEventListener('resize', () => ask(''));
/* the reading is playing when the FRAME says it is — not when this leaf
   thinks it is. Starting playback from the transport is a gesture the leaf
   never sees, and it drove nothing for as long as this kept its own flag. */
/* The clock asks as often as it can, and the server paces it in real
   seconds — `ask` serialises, so this self-throttles to the round trip
   instead of lurching at whatever the interval happened to be. */
setInterval(() => { if (frame && frame.running) ask('tick'); }, 16);
ask(asked.get('pin') ? `set pin.span ${asked.get('pin')}` : '');
