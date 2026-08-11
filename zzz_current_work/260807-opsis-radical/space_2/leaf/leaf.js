/* opsis — the thin leaf.

   It paints marks and reports gestures. That is the whole of it: no window
   maths, no tint, no layout, no hit geometry of its own, no idea what a
   grammar is. Everything it draws arrives in pixels with a named tone, and
   everything the hand does goes back as an address.

   space_1 kept "the window, the cursor and the tint" on this side, which
   meant two geometries that had to agree — and every late failure there was
   them disagreeing. Here there is only one, and it is not here. */

'use strict';

const TONE = {
  head: '#0e131c', hair: '#232b3a', ink: '#c9d4df', dim: '#66707f',
  label: '#6fc3c9', title: '#e8e2d6', good: '#79c99a', bad: '#e06060',
  closed: '#10282e', live: '#e2a65c', ahead: '#2a3140', cursor: '#e2a65c',
};

const paper = document.getElementById('paper');
let frame = null;          // { marks, hits, w, h }
let asking = false;

function ink(name) { return TONE[name] || '#8fa3b8'; }

async function ask(gesture) {
  if (asking) return;
  asking = true;
  try {
    const box = paper.getBoundingClientRect();
    const said = await fetch('/frame', {
      method: 'POST',
      body: `size ${Math.round(box.width)} ${Math.round(box.height)}\n${gesture || ''}`,
    }).then((r) => r.text());
    frame = read(said);
    paint();
  } finally {
    asking = false;
  }
}

function read(said) {
  const lines = said.split('\n');
  const head = (lines[0] || '').split(' ');
  if (head[0] !== '#FRAME') return frame;
  const count = +head[4] || 0;
  const marks = lines.slice(1, 1 + count);
  const rest = lines.slice(1 + count);
  const hits = rest[0] && rest[0].startsWith('#HITS ')
    ? rest.slice(1, 1 + (+rest[0].split(' ')[1] || 0)).map((row) => {
      const p = row.split(' ');
      return { x: +p[0], y: +p[1], w: +p[2], h: +p[3], kind: p[4], goes: p[5] };
    })
    : [];
  return { marks, hits, w: +head[1], h: +head[2] };
}

function paint() {
  if (!frame) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = paper.clientWidth, h = paper.clientHeight;
  if (paper.width !== w * dpr || paper.height !== h * dpr) {
    paper.width = w * dpr;
    paper.height = h * dpr;
  }
  const cx = paper.getContext('2d');
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx.clearRect(0, 0, w, h);
  cx.font = '12.5px ui-monospace, "Cascadia Mono", monospace';
  cx.textBaseline = 'alphabetic';
  for (const mark of frame.marks) {
    const p = mark.split(' ');
    if (p[0] === 'box') {
      cx.fillStyle = ink(p[5]);
      cx.fillRect(+p[1], +p[2], +p[3], +p[4]);
      if (p[5] !== 'head') {
        cx.strokeStyle = ink(p[5] === 'closed' ? 'label' : p[5]);
        cx.strokeRect(+p[1] + 0.5, +p[2] + 0.5, Math.max(+p[3] - 1, 1), +p[4]);
      }
    } else if (p[0] === 'line') {
      cx.strokeStyle = ink(p[5]);
      cx.beginPath();
      cx.moveTo(+p[1], +p[2]);
      cx.lineTo(+p[3], +p[4]);
      cx.stroke();
    } else if (p[0] === 'text') {
      cx.fillStyle = ink(p[3]);
      cx.fillText(p.slice(4).join(' '), +p[1], +p[2]);
    }
  }
}

function under(ev) {
  const box = paper.getBoundingClientRect();
  const x = ev.clientX - box.left, y = ev.clientY - box.top;
  return (frame ? frame.hits : []).find(
    (h) => x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h);
}

paper.addEventListener('click', (ev) => {
  const target = under(ev);
  if (target) ask(`at ${target.kind} ${target.goes}`);
});

let dragging = false;
paper.addEventListener('pointerdown', (ev) => { dragging = true; scrub(ev); });
window.addEventListener('pointerup', () => { dragging = false; });
paper.addEventListener('pointermove', (ev) => { if (dragging) scrub(ev); });

function scrub(ev) {
  const box = paper.getBoundingClientRect();
  ask(`point ${Math.round(ev.clientX - box.left)} ${Math.round(ev.clientY - box.top)}`);
}

window.addEventListener('keydown', (ev) => {
  const said = { ' ': 'play', ArrowRight: 'step 1', ArrowLeft: 'step -1',
                 Home: 'go 0', End: 'go end' }[ev.key];
  if (said) { ev.preventDefault(); ask(said); }
});

window.addEventListener('resize', () => ask('resized'));
ask('');
setInterval(() => { if (playing) ask('tick'); }, 120);
let playing = false;
