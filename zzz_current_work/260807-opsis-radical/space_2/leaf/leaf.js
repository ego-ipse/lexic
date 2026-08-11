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
const asked = new URLSearchParams(location.search);
const only = asked.get('only') || '';
/* a window looks through its own layer over the session's policy: its view,
   its camera, its scroll are its own, and the cursor stays everyone's */
const win = asked.get('win') || '';

let frame = null;
let asking = false;
let queued = null;
let playing = false;
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
    if (got) { frame = got; paint(); weld(); }
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
  const fills = {}, edges = {}, fonts = {};
  const into = { fill: fills, edge: edges, font: fonts };
  for (const row of lines.slice(2, 2 + tones)) {
    const p = row.split(' ');
    if (into[p[0]]) into[p[0]][p[1]] = p.slice(2).join(' ');
  }
  let i = 2 + tones;
  const head = (lines[i] || '').split(' ');
  if (head[0] !== '#FRAME') return null;
  const count = +head[4] || 0;
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
  return { font, fills, edges, fonts, marks, hits, planes: shown, over: above };
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
    } else if (p[0] === 'text') {
      cx.font = face(p[4]);
      cx.fillStyle = fill(p[3]);
      cx.textAlign = p[5] === 'r' ? 'right' : 'left';
      cx.fillText(p.slice(6).join(' '), +p[1], +p[2]);
      cx.textAlign = 'left';
    }
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
  if (target.kind === 'pin') {
    const id = `pin-${target.goes.replace(':', '-')}`;
    window.open(`/?only=pin&win=${id}&pin=${target.goes}`, '_blank',
                'width=520,height=380');
    return;
  }
  if (target.kind === 'pop') {
    const id = `${target.goes}-${held.size}-${frame.marks.length}`;
    window.open(`/?only=${target.goes}&win=${id}`, '_blank', 'width=1000,height=760');
    return;
  }
  if (target.kind.includes('.')) {
    ask(`set ${target.kind} ${target.goes}`);
    return;
  }
  ask(`at ${target.kind} ${target.goes}${into}`);
});

/* dragging: a seam resizes, anything else in a picture turns it */
paper.addEventListener('pointerdown', (ev) => {
  dragging = { x: ev.clientX, y: ev.clientY, on: under(ev, false) };
});
window.addEventListener('pointerup', () => { dragging = null; });
window.addEventListener('pointermove', (ev) => {
  if (!dragging) return;
  const dx = ev.clientX - dragging.x, dy = ev.clientY - dragging.y;
  if (Math.abs(dx) + Math.abs(dy) < 3) return;
  dragging.x = ev.clientX; dragging.y = ev.clientY;
  const on = dragging.on;
  if (on && on.kind.startsWith('dial.')) {
    const box = paper.getBoundingClientRect();
    const part = (ev.clientX - box.left - on.x) / on.w;
    ask(`dial ${on.kind.slice(5)} ${on.goes} ${Math.max(0, Math.min(1, part)).toFixed(3)}`);
    return;
  }
  if (on && on.kind === 'seam') {
    const box = paper.getBoundingClientRect();
    const part = on.w < on.h
      ? (ev.clientX - box.left) / box.width
      : (ev.clientY - box.top) / box.height;
    ask(`seam ${on.goes} ${part.toFixed(3)}`);
    return;
  }
  ask(`spin ${dx} ${dy}`);
});

/* a stack of diagrams reads like a document: wheel scrolls, Ctrl+wheel zooms */
paper.addEventListener('wheel', (ev) => {
  const target = under(ev, true);
  if (!target) return;
  ev.preventDefault();
  const by = ev.deltaY > 0 ? 1 : -1;
  ask(`${ev.ctrlKey ? 'zoom' : 'scroll'} ${target.goes} ${by}`);
}, { passive: false });

/* Keys are REPORTED, not interpreted: whether Space is a letter or the
   transport depends on what has the hand, and that is not known here. */
const NAMED = new Set(['Space', 'Escape', 'Home', 'End', 'ArrowLeft', 'ArrowRight',
                       'Ctrl+Enter', 'Ctrl+s']);
window.addEventListener('keydown', (ev) => {
  const typing = document.activeElement && document.activeElement.classList.contains('plane');
  const name = (ev.ctrlKey ? 'Ctrl+' : '') + (ev.key === ' ' ? 'Space' : ev.key);
  if (typing && !ev.ctrlKey && name !== 'Escape') return;
  if (!NAMED.has(name)) return;
  ev.preventDefault();
  if (name === 'Space' && !typing) playing = !playing;
  ask(`key ${name}`);
});

window.addEventListener('resize', () => ask(''));
setInterval(() => { if (playing) ask('tick'); }, 110);
ask(asked.get('pin') ? `set pin.span ${asked.get('pin')}` : '');
