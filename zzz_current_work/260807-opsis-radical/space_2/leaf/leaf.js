/* opsis — the thin leaf. It paints marks and reports gestures.

   No window maths, no tint, no layout, no hit geometry, and no idea what a
   grammar is. One geometry exists and it is not here, which is why nothing
   here can disagree with the picture. */

'use strict';

const paper = document.getElementById('paper');
let frame = null;
let asking = false;
let queued = null;
let playing = false;
const only = new URLSearchParams(location.search).get('only') || '';

const fill = (name) => (frame.fills[name] || frame.fills.dim);
const face = (name) => (frame.fonts[name] || frame.font);
const edge = (name) => frame.edges[name];

/* A gesture that arrives mid-flight is NOT dropped: scrolls and steps add up
   and the last one wins, so a fast hand is answered instead of ignored. */
async function ask(gesture) {
  if (asking) { queued = merge(queued, gesture); return; }
  asking = true;
  try {
    const box = paper.getBoundingClientRect();
    const said = await fetch('/frame', {
      method: 'POST',
      body: `size ${Math.round(box.width)} ${Math.round(box.height)}\n`
        + `${only ? `only ${only}\n` : ''}${gesture || ''}`,
    }).then((r) => r.text());
    const got = read(said);
    if (got) { frame = got; paint(); }
  } finally {
    asking = false;
    if (queued !== null) { const next = queued; queued = null; ask(next); }
  }
}

/* two of the same kind of nudge are one bigger nudge */
function merge(waiting, gesture) {
  if (!waiting) return gesture;
  const a = waiting.split(' '), b = (gesture || '').split(' ');
  if (a[0] === b[0] && (a[0] === 'scroll' || a[0] === 'spin') && a[1] === b[1]) {
    return [...a.slice(0, 2), ...a.slice(2).map((n, i) => +n + +b[i + 2])].join(' ');
  }
  if (a[0] === 'step' && b[0] === 'step') return `step ${+a[1] + +b[1]}`;
  return gesture;
}

function read(said) {
  const lines = said.split('\n');
  const font = (lines[0] || '').startsWith('#FONT ') ? lines[0].slice(6) : '';
  const tones = +(lines[1] || '').split(' ')[1] || 0;
  const fills = {}, edges = {}, fonts = {};
  for (const row of lines.slice(2, 2 + tones)) {
    const p = row.split(' ');
    ({ edge: edges, font: fonts, fill: fills })[p[0]][p[1]] = p.slice(2).join(' ');
  }
  const lead = 2 + tones;
  const head = (lines[lead] || '').split(' ');
  if (head[0] !== '#FRAME') return null;
  const count = +head[4] || 0;
  const rest = lines.slice(lead + 1 + count);
  return {
    font, fills, edges, fonts,
    marks: lines.slice(lead + 1, lead + 1 + count),
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
  cx.font = frame.font;
  for (const mark of frame.marks) {
    const p = mark.split(' ');
    if (p[0] === 'box') {
      cx.fillStyle = fill(p[5]);
      cx.fillRect(+p[1], +p[2], +p[3], +p[4]);
      const around = edge(p[5]);
      if (around) {
        cx.strokeStyle = around;
        cx.strokeRect(+p[1] + 0.5, +p[2] + 0.5, Math.max(+p[3] - 1, 1), +p[4]);
      }
    } else if (p[0] === 'line') {
      cx.strokeStyle = fill(p[5]);
      cx.beginPath();
      cx.moveTo(+p[1], +p[2]);
      cx.lineTo(+p[3], +p[4]);
      cx.stroke();
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
      cx.beginPath();
      cx.arc(+p[1], +p[2], +p[3], 0, Math.PI * 2);
      cx.stroke();
    } else if (p[0] === 'text') {
      cx.font = face(p[3]);
      cx.fillStyle = fill(p[3]);
      cx.fillText(p.slice(4).join(' '), +p[1], +p[2]);
    }
  }
}

function under(ev, wanted) {
  const box = paper.getBoundingClientRect();
  const x = ev.clientX - box.left, y = ev.clientY - box.top;
  return (frame ? frame.hits : []).find(
    (h) => (h.kind === 'scroll') === wanted
      && x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h);
}

paper.addEventListener('click', (ev) => {
  const target = under(ev, false);
  if (!target) return;
  if (target.kind === 'pop' || target.kind === 'clone') {
    window.open(`/?only=${target.goes}`, '_blank', 'width=900,height=700');
    return;
  }
  ask(`at ${target.kind} ${target.goes}`);
});

/* dragging turns whatever is under the hand; what that MEANS is the server's */
let held = null;
paper.addEventListener('pointerdown', (ev) => { held = [ev.clientX, ev.clientY]; });
window.addEventListener('pointerup', () => { held = null; });
window.addEventListener('pointermove', (ev) => {
  if (!held) return;
  const dx = ev.clientX - held[0], dy = ev.clientY - held[1];
  if (Math.abs(dx) + Math.abs(dy) < 3) return;
  held = [ev.clientX, ev.clientY];
  ask(`spin ${dx} ${dy}`);
});

paper.addEventListener('wheel', (ev) => {
  ev.preventDefault();
  const target = under(ev, true);
  if (target) ask(`scroll ${target.goes} ${ev.deltaY > 0 ? 1 : -1}`);
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
setInterval(() => { if (playing) ask('tick'); }, 110);  // the pace is the server's; this only wakes it
ask('');
