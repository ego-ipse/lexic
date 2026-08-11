/* opsis — the thin leaf. It paints marks and reports gestures.

   No window maths, no tint, no layout, no hit geometry, and no idea what a
   grammar is. One geometry exists and it is not here, which is why nothing
   here can disagree with the picture. */

'use strict';

const TONE = {
  head: '#0e131c', hair: '#232b3a', ink: '#c9d4df', dim: '#66707f',
  label: '#6fc3c9', title: '#e8e2d6', good: '#79c99a', bad: '#e06060',
  closed: '#10282e', live: '#e2a65c', ahead: '#2a3140', cursor: '#e2a65c',
  lit: '#141b26', lost: '#4a1f22', rail: '#6fc3c9', loop: '#d98cf5',
  token: '#8fa3b8', ref: '#6fc3c9', class: '#d98cf5', name: '#e2a65c',
  hot: '#e2a65c', cool: 'rgba(111,195,201,0.18)', seen: '#4a5568',
  eps: '#3a4250', kept: '#8fa3b8', modelband0: '#0e151d', modelband1: '#152230',
  modelband2: '#1d3143', modelband3: '#274257',
};

const paper = document.getElementById('paper');
let frame = null;
let asking = false;
let playing = false;

const ink = (name) => TONE[name] || '#8fa3b8';

async function ask(gesture) {
  if (asking) return;
  asking = true;
  try {
    const box = paper.getBoundingClientRect();
    const said = await fetch('/frame', {
      method: 'POST',
      body: `size ${Math.round(box.width)} ${Math.round(box.height)}\n${gesture || ''}`,
    }).then((r) => r.text());
    const got = read(said);
    if (got) { frame = got; paint(); }
  } finally { asking = false; }
}

function read(said) {
  const lines = said.split('\n');
  const head = (lines[0] || '').split(' ');
  if (head[0] !== '#FRAME') return null;
  const count = +head[4] || 0;
  const rest = lines.slice(1 + count);
  return {
    marks: lines.slice(1, 1 + count),
    hits: rest[0] && rest[0].startsWith('#HITS ')
      ? rest.slice(1, 1 + (+rest[0].split(' ')[1] || 0)).map((row) => {
        const p = row.split(' ');
        return { x: +p[0], y: +p[1], w: +p[2], h: +p[3], kind: p[4], goes: p[5] };
      })
      : [],
  };
}

function paint() {
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
  for (const mark of frame.marks) {
    const p = mark.split(' ');
    if (p[0] === 'box') {
      const tone = ink(p[5]);
      cx.fillStyle = tone;
      cx.fillRect(+p[1], +p[2], +p[3], +p[4]);
      if (['closed', 'ahead', 'live', 'kept', 'lost'].includes(p[5])) {
        cx.strokeStyle = ink(p[5] === 'closed' ? 'label' : p[5]);
        cx.strokeRect(+p[1] + 0.5, +p[2] + 0.5, Math.max(+p[3] - 1, 1), +p[4]);
      }
      const label = p.slice(6).join(' ');
      if (label) { cx.fillStyle = ink('ink'); cx.fillText(label, +p[1] + 4, +p[2] + 11); }
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

paper.addEventListener('wheel', (ev) => {
  ev.preventDefault();
  const box = paper.getBoundingClientRect();
  const part = (ev.clientX - box.left) / box.width;
  const which = part < 0.34 ? 'reader' : (part < 0.62 ? 'document' : 'surface');
  ask(`scroll ${which} ${ev.deltaY > 0 ? 1 : -1}`);
}, { passive: false });

window.addEventListener('keydown', (ev) => {
  const said = { ' ': 'play', ArrowRight: 'step 1', ArrowLeft: 'step -1',
                 Home: 'go 0', End: 'go end' }[ev.key];
  if (!said) return;
  ev.preventDefault();
  if (said === 'play') playing = !playing;
  ask(said);
});

window.addEventListener('resize', () => ask('resized'));
setInterval(() => { if (playing) ask('tick'); }, 110);
ask('');
